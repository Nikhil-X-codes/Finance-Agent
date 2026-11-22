"""Stream completed LangGraph report steps and the report payload."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.config.settings import settings
from src.config.models import GenerateReportRequest
from src.core.rate_limit import limiter
from src.api.sse import stream_event

router = APIRouter()
PROGRESS = {
    "parser": "Portfolio holdings normalized",
    "enricher": "Market context checked",
    "portfolio_context": "Portfolio facts calculated",
    "risk_analyzer": "Concentration assessed",
    "recommender": "Advisory analysis completed",
    "output": "Report formatted",
}


@router.post("/generate-report")
@limiter.limit(f"{settings.report_rate_limit_per_minute}/minute")
async def generate_report(request: Request, payload: GenerateReportRequest) -> StreamingResponse:
    initial = {
        "include_news": payload.include_news,
        "raw_holdings": payload.portfolio,
    }

    async def events():
        report = None
        try:
            yield stream_event("status", {"node": "start", "message": "Starting portfolio report"})
            async for update in request.app.state.report_graph.astream(initial, stream_mode="updates"):
                for node, values in update.items():
                    if node in PROGRESS:
                        yield stream_event("status", {"node": node, "message": PROGRESS[node]})
                    if node == "output":
                        report = values.get("report_json")
            if not report:
                raise RuntimeError("Graph finished without a report")
            yield stream_event("complete", {
                "reportId": report["id"], "generatedVia": report["generatedVia"],
                "createdAt": report["createdAt"], "report_json": report,
            })
        except Exception:
            yield stream_event("error", {"error": "Report generation failed.", "code": "GENERATION_FAILED"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
