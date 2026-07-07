"""LangGraph router edge."""

from __future__ import annotations

from typing import Literal

from ..state import PortfolioState


def route_request(state: PortfolioState) -> Literal["parser", "qa_retriever", "trade_validator"]:
    """Route request based on request_type."""
    request_type = state.get("request_type")
    if request_type == "QA":
        return "qa_retriever"
    elif request_type == "TRADE_VALIDATE":
        return "trade_validator"
    # Default to parser node (which is the start of the report generation flow)
    return "parser"
