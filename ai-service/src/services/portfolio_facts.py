"""Read shared portfolio facts for reports and grounded Q&A."""

from collections import defaultdict


def invested_cost(holding: dict) -> float:
    cost = holding.get("invested_cost")
    return cost if cost is not None else round(holding["quantity"] * holding["avg_buy_price"], 2)


def is_active(holding: dict) -> bool:
    return holding.get("status") != "REALIZED" and holding.get("quantity", 0) > 0


def summarize_portfolio(holdings: list[dict]) -> dict:
    active = [holding for holding in holdings if is_active(holding)]
    realized = [holding for holding in holdings if holding.get("status") == "REALIZED"]
    total_cost = round(sum(invested_cost(holding) for holding in active), 2)

    values = []
    for holding in active:
        price = holding.get("current_price")
        value = holding.get("market_value")
        values.append(None if price is None else value if value is not None else round(holding["quantity"] * price, 2))

    market_value = round(sum(values), 2) if None not in values else None
    realized_values = [holding.get("realized_pnl") for holding in realized]
    realized_total = round(sum(realized_values), 2) if None not in realized_values else None
    sector_costs: dict[str, float] = defaultdict(float)
    for holding in active:
        sector_costs[holding.get("sector") or "Other"] += invested_cost(holding)

    return {
        "total_invested": total_cost,
        "total_current": market_value,
        "realized_pnl": realized_total,
        "unrealized_pnl": round(market_value - total_cost, 2) if market_value is not None else None,
        "sector_weights": {
            sector: cost / total_cost if total_cost else 0 for sector, cost in sector_costs.items()
        },
        "holding_count": len(active),
    }
