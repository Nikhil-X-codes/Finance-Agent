"""FastAPI route for report generation with SSE streaming."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.config.constants import REPORT_RATE_LIMIT_PER_MINUTE
from src.config.models import GenerateReportRequest
from src.core.graph import agent_graph, tracer
from src.core.rate_limit import limiter

router = APIRouter()


@limiter.limit(f"{REPORT_RATE_LIMIT_PER_MINUTE}/minute")
@router.post("/generate-report")
async def generate_report(request: Request, payload: GenerateReportRequest) -> StreamingResponse:
    """Generate advisory report and stream progress and markdown chunks using Server-Sent Events (SSE)."""
    initial_state = {
        "user_id": payload.user_id,
        "request_type": "REPORT",
        "include_news": payload.include_news,
        "raw_holdings": [h.model_dump() for h in payload.portfolio],
        "errors": [],
        "current_node": "start"
    }

    async def event_generator():
        try:
            # Yield initial status
            yield "event: status\ndata: {\"node\": \"parser\", \"message\": \"Initializing portfolio parsing...\"}\n\n"
            
            # Setup thread ID for graph checkpointer
            config = {
                "configurable": {"thread_id": f"report-{payload.user_id}-{uuid.uuid4().hex[:8]}"},
                "callbacks": [tracer]
            }
            
            # Dictionary to capture final values from the generator
            output_ref = {"report_json": {}, "report_markdown": ""}
            
            # Helper to parse and stream events from a stream generator
            async def stream_and_yield(stream):
                async for event in stream:
                    kind = event.get("event")
                    name = event.get("name")
                    
                    if kind == "on_node_start":
                        node_name = name
                        message = f"Executing {node_name}..."
                        if node_name == "parser":
                            message = "Normalizing portfolio holdings..."
                        elif node_name == "enricher":
                            message = f"Fetching market data for {len(payload.portfolio)} holdings..."
                        elif node_name == "rag_retriever":
                            message = "Retrieving regulatory guidelines..."
                        elif node_name == "risk_analyzer":
                            message = "Analyzing portfolio risks and guidelines..."
                        elif node_name == "recommender":
                            message = "Generating advisory recommendations..."
                        elif node_name == "output":
                            message = "Formatting final report..."
                            
                        yield f"event: status\ndata: {json.dumps({'node': node_name, 'message': message})}\n\n"
                        
                    elif kind == "on_node_end" and name == "output":
                        # Extract the report outputs from state
                        output_data = event.get("data", {}).get("output", {})
                        output_ref["report_json"] = output_data.get("report_json", {})
                        output_ref["report_markdown"] = output_data.get("report_markdown", "")

            # 1. Run initial graph stream (this will run the parser node and then interrupt/pause)
            initial_stream = agent_graph.astream_events(initial_state, config, version="v2")
            async for status_update in stream_and_yield(initial_stream):
                yield status_update

            # 2. Automatically resume the graph (since we want it to run to completion for the report generation endpoint)
            # Passing None as input resumes from the checkpoint
            resume_stream = agent_graph.astream_events(None, config, version="v2")
            
            final_json = {}
            final_markdown = ""
            async for update in stream_and_yield(resume_stream):
                # Check if it is a status message (which starts with 'event: status')
                if update.startswith("event: status"):
                    yield update
                else:
                    # It might be the return value of stream_and_yield if we were able to return it.
                    # Since this is an async generator, we capture the final values from the generator end
                    pass
            
            # Get the state to extract the final markdown and json
            state_result = await agent_graph.aget_state(config)
            report_json = state_result.values.get("report_json") or {}
            report_markdown = state_result.values.get("report_markdown") or ""
            
            if report_markdown:
                # Yield the markdown in small chunks to simulate smooth streaming
                chunk_size = 120
                for i in range(0, len(report_markdown), chunk_size):
                    chunk = report_markdown[i:i+chunk_size]
                    yield f"event: markdown_chunk\ndata: {json.dumps({'chunk': chunk})}\n\n"
                    await asyncio.sleep(0.01)  # 10ms delay between chunks
                    
                # Yield complete event
                complete_data = {
                    "reportId": report_json.get("id"),
                    "generatedVia": report_json.get("generatedVia"),
                    "createdAt": report_json.get("createdAt"),
                    "report_json": report_json
                }
                yield f"event: complete\ndata: {json.dumps(complete_data)}\n\n"
                    
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'code': 'GENERATION_FAILED'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
