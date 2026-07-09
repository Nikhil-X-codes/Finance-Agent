"""LangGraph state schema for Indian Portfolio Advisor."""

from __future__ import annotations

from typing import Any, TypedDict

from src.config.models import Holding


class PortfolioState(TypedDict, total=False):
    # Input parameters
    user_id: str
    request_type: str  # "REPORT" | "QA" | "TRADE_VALIDATE"
    include_news: bool
    question: str  # For Q&A request type
    conversation_history: list[dict[str, Any]]  # For Q&A request type

    # Raw user holdings input
    raw_holdings: list[dict[str, Any]]

    # Intermediate states
    normalized_holdings: list[Holding]
    enriched_holdings: list[dict[str, Any]]
    macro_context: dict[str, Any]
    risk_flags: list[dict[str, Any]]
    generated_via: str  # "LLM" | "RULE_BASED"
    proposed_trade: dict[str, Any]  # proposed trade input

    # Final outputs
    recommendations: dict[str, Any]
    report_markdown: str
    report_json: dict[str, Any]
    qa_response: str
    question_type: str  # "portfolio" | "general"
    qa_citations: list[dict[str, Any]]
    validation_result: dict[str, Any]  # output of trade validator

    # New portfolio context and summary fields
    portfolio_context_text: str
    portfolio_summary: dict[str, Any]
    qa_context_text: str
    target_holdings: list[str]

    # Control/debugging fields
    errors: list[dict[str, str]]
    current_node: str
