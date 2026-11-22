"""FastAPI route for proposed trade validation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.config.models import Holding
from src.services.trade_review import review_trade

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
    return await review_trade(
        payload.proposed_trade.model_dump(), [h.model_dump(mode="json") for h in payload.portfolio],
    )
