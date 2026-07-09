"""FastAPI route for portfolio Q&A with SSE streaming."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.config.constants import QA_RATE_LIMIT_PER_MINUTE
from src.config.models import QARequest
from src.core.graph import agent_graph, tracer
from src.core.rate_limit import limiter

router = APIRouter()


@limiter.limit(f"{QA_RATE_LIMIT_PER_MINUTE}/minute")
@router.post("/qa")
async def qa(request: Request, payload: QARequest) -> StreamingResponse:
    """Submit a question about portfolio and stream responses and citations back using SSE."""
    initial_state = {
        "user_id": payload.user_id,
        "request_type": "QA",
        "question": payload.question,
        "conversation_history": payload.conversation_history or [],
        "raw_holdings": [h.model_dump() for h in (payload.portfolio_context or [])],
        "errors": [],
        "current_node": "start"
    }

    async def qa_event_generator():
        try:
            config = {
                "configurable": {"thread_id": f"qa-{payload.user_id}-{uuid.uuid4().hex[:8]}"},
                "callbacks": [tracer]
            }
            
            # Execute the QA agent subgraph
            state_result = await agent_graph.ainvoke(initial_state, config)
            
            qa_response = state_result.get("qa_response") or "No response generated."
            qa_citations = state_result.get("qa_citations") or []
            
            # Stream the response text in small word packets
            words = qa_response.split(" ")
            chunk = ""
            for word in words:
                chunk += word + " "
                if len(chunk) > 20:
                    yield f"event: chunk\ndata: {json.dumps({'text': chunk})}\n\n"
                    chunk = ""
                    await asyncio.sleep(0.02)  # 20ms delay
            if chunk:
                yield f"event: chunk\ndata: {json.dumps({'text': chunk})}\n\n"
                
            # Yield complete event
            complete_data = {
                "fullText": qa_response,
                "citations": qa_citations,
                "questionType": state_result.get("question_type") or "general"
            }
            yield f"event: complete\ndata: {json.dumps(complete_data)}\n\n"
            
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'code': 'GENERATION_FAILED'})}\n\n"

    return StreamingResponse(qa_event_generator(), media_type="text/event-stream")
