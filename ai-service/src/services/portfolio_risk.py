"""One deterministic concentration policy for both dashboard and reports."""

from collections import defaultdict
from typing import Any

from src.config.models import Holding


def assess_portfolio_risk(holdings: list[Holding]) -> dict[str, Any]:
    active = [h for h in holdings if h.status != "REALIZED" and h.quantity > 0]
    by_ticker: dict[str, float] = defaultdict(float)
    by_sector: dict[str, float] = defaultdict(float)
    known_sector_cost = 0.0
    for h in active:
        cost = h.invested_cost if h.invested_cost is not None else round(h.quantity * h.avg_buy_price, 2)
        by_ticker[h.ticker] += cost
        sector = (h.sector or "").strip()
        if sector.casefold() not in {"", "unknown", "other"}:
            by_sector[sector] += cost
            known_sector_cost += cost

    total = sum(by_ticker.values())
    if not total:
        return {
            "overall_risk": "UNAVAILABLE",
            "reasoning": "Concentration is unavailable without active positions and invested cost.",
            "flags": [],
            "sector_coverage": None,
            "largest_holdings": [],
            "top_two_weight": None,
        }

    flags = []
    for kind, amounts, moderate, high in (
        ("HOLDING_CONCENTRATION", by_ticker, 0.25, 0.40),
        ("SECTOR_CONCENTRATION", by_sector, 0.45, 0.60),
    ):
        for name, cost in sorted(amounts.items()):
            weight = cost / total
            if weight < moderate:
                continue
            flags.append({
                "type": kind,
                "ticker": name if kind == "HOLDING_CONCENTRATION" else "PORTFOLIO",
                "severity": "HIGH" if weight >= high else "MEDIUM",
                "description": f"{name} represents {weight:.1%} of invested cost.",
                "portfolio_weight": weight,
                "citation": "Finance Agent concentration policy",
            })

    overall = "HIGH" if any(f["severity"] == "HIGH" for f in flags) else "MEDIUM" if flags else "LOW"
    largest = sorted(by_ticker.items(), key=lambda item: (-item[1], item[0]))[:2]
    return {
        "overall_risk": overall,
        "reasoning": "Concentration assessment based on invested cost and known sectors.",
        "flags": flags,
        "sector_coverage": known_sector_cost / total,
        "largest_holdings": [{"ticker": ticker, "weight": cost / total} for ticker, cost in largest],
        "top_two_weight": sum(cost for _, cost in largest) / total if len(largest) == 2 else None,
    }
