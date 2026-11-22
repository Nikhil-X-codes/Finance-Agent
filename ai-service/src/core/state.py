"""State carried through the report workflow."""

from __future__ import annotations

from typing import Any, TypedDict

from src.config.models import Holding


class ReportState(TypedDict, total=False):
    include_news: bool
    raw_holdings: list[Holding]
    normalized_holdings: list[Holding]
    enriched_holdings: list[dict[str, Any]]
    overall_risk: str
    risk_flags: list[dict[str, Any]]
    concentration: dict[str, Any]
    generated_via: str
    recommendations: list[dict[str, Any]]
    report_json: dict[str, Any]
    portfolio_summary: dict[str, Any]
    report_news: list[dict[str, Any]]
    market_snapshot: dict[str, Any]
