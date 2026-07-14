"""Conditional edge functions and routing logic for the LangGraph pipeline."""

from __future__ import annotations

from typing import Any

from ..state import PortfolioState


def route_recommender(state: PortfolioState) -> str:
    """Router edge to determine whether we skip the recommender node on severe parsing errors."""
    errors = state.get("errors") or []
    # If we have fatal parser or enricher errors that leave us with no holdings, go straight to output
    normalized = state.get("normalized_holdings") or []
    if not normalized:
        return "output"
    return "recommender"


def route_portfolio_context(state: PortfolioState) -> str:
    """Route after portfolio context builder based on request type."""
    request_type = state.get("request_type")
    if request_type == "QA":
        return "qa_generator"
    return "risk_analyzer"
