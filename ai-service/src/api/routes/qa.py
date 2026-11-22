"""Stream Q&A workflow progress and its completed, cited answer."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.config.settings import settings
from src.config.models import QARequest
from src.core.qa_graph import default_qa_providers
from src.core.rate_limit import limiter
from src.api.sse import stream_event

router = APIRouter()
PROGRESS = {
    "parse_question": "Question classified",
    "retrieve_portfolio": "Portfolio records checked",
    "retrieve_market": "Market data checked",
    "check_evidence": "Evidence reviewed",
}


@router.post("/qa")
@limiter.limit(f"{settings.qa_rate_limit_per_minute}/minute")
async def qa(request: Request, payload: QARequest) -> StreamingResponse:
    initial = {
        "question": payload.question,
        "conversation_history": [turn.model_dump() for turn in payload.conversation_history],
        "raw_holdings": [h.model_dump(mode="json") for h in payload.portfolio_context or []],
    }

    async def events():
        result = {}
        try:
            yield stream_event("status", {"node": "start", "message": "Reading your question"})
            async for update in request.app.state.qa_graph.astream(initial, context=default_qa_providers(), stream_mode="updates"):
                for node, values in update.items():
                    result.update(values or {})
                    if node in PROGRESS:
                        yield stream_event("status", {"node": node, "message": PROGRESS[node]})
            yield stream_event("complete", {
                "fullText": result["qa_response"], "citations": result["qa_citations"],
                "questionType": result["question_type"], "answerStatus": result["answer_status"],
            })
        except Exception:
            yield stream_event("error", {"error": "Q&A is temporarily unavailable.", "code": "GENERATION_FAILED"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
