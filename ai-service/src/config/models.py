"""Pydantic models for the AI service API contract."""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Holding(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    isin: str | None = None
    ticker: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1)]
    quantity: Annotated[float, Field(ge=0)]
    avg_buy_price: Annotated[float, Field(ge=0)]
    asset_type: str | None = None
    sector: str | None = None
    status: str | None = "UNREALIZED"
    current_price: float | None = Field(None, ge=0)
    invested_cost: float | None = Field(None, ge=0)
    market_value: float | None = Field(None, ge=0)
    price_source: str | None = None
    price_as_of: str | None = None
    buy_date: date | None = None
    sell_date: date | None = None
    sell_price: float | None = None
    realized_pnl: float | None = None


class RealizedTrade(BaseModel):
    """A completed/sold trade for tax/P&L tracking."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    isin: str | None = None
    ticker: Annotated[str, Field(min_length=1, max_length=100)]
    name: str
    quantity: float = Field(gt=0)
    buy_price: float = Field(ge=0)
    sell_price: float | None = Field(None, ge=0)
    buy_date: date | None = None
    sell_date: date | None = None
    realized_pnl: float | None = None


class ParseStatementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    broker_detected: Annotated[str, Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    coverage_start: date | None = None
    coverage_end: date | None = None
    holdings: list[Holding] = Field(default_factory=list)
    realized_trades: list[RealizedTrade] = Field(default_factory=list)
    unrecognized_rows: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | None = None


class GenerateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    user_id: Annotated[str, Field(min_length=1)]
    portfolio: list[Holding]
    include_news: bool = True


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class QARequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    user_id: Annotated[str, Field(min_length=1)]
    question: Annotated[str, Field(min_length=1, max_length=3000)]
    portfolio_context: list[Holding] | None = None
    conversation_history: list[ConversationTurn] = Field(default_factory=list, max_length=8)
