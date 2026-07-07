"""FastAPI route for proposed trade validation."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.config.models import Holding
from src.core.graph import agent_graph, tracer

router = APIRouter()


class ProposedTrade(BaseModel):
    ticker: str = Field(..., min_length=1)
    action: str = Field(..., pattern="^(BUY|SELL|TRIM|EXIT)$")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)


class ValidateTradeRequest(BaseModel):
    user_id: str
    proposed_trade: ProposedTrade
    portfolio: list[Holding] = Field(default_factory=list)


@router.post("/validate-trade")
async def validate_proposed_trade(payload: ValidateTradeRequest) -> dict[str, Any]:
    """Validate a proposed trade against regulatory guidelines by invoking the trade_validator node."""
    initial_state = {
        "user_id": payload.user_id,
        "request_type": "TRADE_VALIDATE",
        "proposed_trade": payload.proposed_trade.model_dump(),
        "raw_holdings": [h.model_dump() for h in payload.portfolio],
        "errors": [],
        "current_node": "start"
    }

    config = {
        "configurable": {"thread_id": f"trade-{payload.user_id}-{uuid.uuid4().hex[:8]}"},
        "callbacks": [tracer]
    }
    
    # Run the trade validator node in the graph
    state_result = await agent_graph.ainvoke(initial_state, config)
    
    return state_result.get("validation_result") or {
        "allowed": False,
        "warnings": ["Trade validation failed to produce a result."],
        "new_portfolio_weight": 0.0
    }
