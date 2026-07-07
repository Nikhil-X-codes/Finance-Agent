"""Pydantic models for the AI service API contract."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class Holding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isin: str | None = None
    ticker: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1)]
    quantity: Annotated[float, Field(ge=0)]
    avg_buy_price: Annotated[float, Field(ge=0)]
    asset_type: str | None = None
    sector: str | None = None
    status: str | None = "UNREALIZED"
    current_price: float | None = None
    sell_price: float | None = None
    realized_pnl: float | None = None


class RealizedTrade(BaseModel):
    """A completed/sold trade for tax/P&L tracking."""
    model_config = ConfigDict(extra="forbid")

    isin: str
    ticker: str
    name: str
    quantity: float = Field(gt=0)
    buy_price: float = Field(ge=0)
    sell_price: float = Field(ge=0)
    buy_date: str | None = None
    sell_date: str | None = None
    realized_pnl: float | None = None


class ParseStatementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker_detected: Annotated[str, Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    holdings: list[Holding] = Field(default_factory=list)
    realized_trades: list[RealizedTrade] = Field(default_factory=list)
    unrecognized_rows: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | None = None


class GenerateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: Annotated[str, Field(min_length=1)]
    portfolio: list[Holding]
    include_news: bool = True


class QARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: Annotated[str, Field(min_length=1)]
    question: Annotated[str, Field(min_length=1)]
    portfolio_context: list[Holding] | None = None
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)


class EnrichRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers: list[str] = Field(default_factory=list)
    mf_schemes: list[str] = Field(default_factory=list)
    include_news: bool = False
    macro_only: bool = False