"""Apply the shared portfolio concentration policy inside the report graph."""

from typing import Any

from src.services.portfolio_risk import assess_portfolio_risk
from ..state import ReportState


def analyze_portfolio_risk(state: ReportState) -> dict[str, Any]:
    result = assess_portfolio_risk(state.get("normalized_holdings") or [])
    return {
        "overall_risk": result["overall_risk"],
        "concentration": {
            "sectorCoverage": result["sector_coverage"],
            "largestHoldings": result["largest_holdings"],
            "topTwoWeight": result["top_two_weight"],
        },
        "risk_flags": [
            {
                "flag_type": flag["type"],
                "evidence_text": flag["description"],
                "ticker": flag["ticker"],
                "severity": flag["severity"],
                "portfolio_weight": flag["portfolio_weight"],
                "citation": flag["citation"],
            }
            for flag in result["flags"]
        ],
    }
