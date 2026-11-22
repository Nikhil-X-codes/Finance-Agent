"""Q&A graph contracts."""

from dataclasses import dataclass
from datetime import date
from typing import Awaitable, Callable, Literal, TypedDict

from pydantic import BaseModel, Field

Intent = Literal["portfolio", "general", "market", "mixed", "clarify", "current_rules"]
Symbol = str


class ParsedQuestion(BaseModel):
    intent: Intent
    symbols: list[Symbol] = Field(default_factory=list, max_length=4)
    trading_date: date | None = None
    question: str = Field(default="", max_length=4000)
    answer_kind: Literal["explanation", "holding_quantity", "portfolio_value", "unsupported_market_analysis"] = "explanation"


class GroundedAnswer(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=15)


class Evidence(TypedDict):
    id: str
    kind: Literal["portfolio", "market"]
    source: str
    title: str
    date: str | None
    text: str


class QAState(TypedDict, total=False):
    question: str
    conversation_history: list[dict[str, str]]
    raw_holdings: list[dict]
    parsed_question: ParsedQuestion
    evidence: list[Evidence]
    limitations: list[str]
    qa_response: str
    qa_citations: list[dict]
    question_type: Intent
    answer_status: Literal["answered", "clarify", "unavailable"]


@dataclass(frozen=True)
class QAProviders:
    classify: Callable[[str, list[str]], Awaitable[ParsedQuestion]]
    answer: Callable[[ParsedQuestion, list[Evidence]], Awaitable[GroundedAnswer]]
    market: Callable[[str, date | None], Awaitable[dict]]
