"""Deterministic trade checks and optional advisory review."""

import asyncio
import json
from typing import Any

from src.services.llm_service import get_llm
from src.services.portfolio_facts import invested_cost, is_active, summarize_portfolio


async def review_trade(trade: dict, holdings: list[dict]) -> dict[str, Any]:
    ticker = trade["ticker"].strip().upper()
    action = trade["action"].strip().upper()
    quantity = trade["quantity"]
    price = trade["price"]
    active = [holding for holding in holdings if is_active(holding)]
    matches = [
        holding for holding in active
        if ticker in {holding["ticker"].upper(), (holding.get("isin") or "").upper()}
    ]
    held = sum(holding["quantity"] for holding in matches)
    holding_cost = sum(invested_cost(holding) for holding in matches)
    portfolio = summarize_portfolio(active)
    total_cost = portfolio["total_invested"]
    details = {
        "ticker": ticker,
        "proposed_action": action,
        "proposed_quantity": quantity,
        "proposed_price": price,
        "limit_threshold": 0.0,
    }

    if action in {"SELL", "TRIM", "EXIT"}:
        if round(quantity - held, 8) > 0:
            warning = f"The current portfolio only has {held:g} units of {ticker}."
            return {
                **details,
                "allowed": False,
                "status": "blocked",
                "risk_level": "HIGH",
                "reasoning": warning,
                "warnings": [warning],
                "suggested_action": "CANCEL",
                "new_portfolio_weight": 0.0,
            }
        delta = -quantity * holding_cost / held if held else 0.0
    else:
        delta = quantity * price

    post_cost = total_cost + delta
    new_weight = 100 * max(0.0, holding_cost + delta) / post_cost if post_cost > 0 else 0.0
    details["new_portfolio_weight"] = new_weight
    evidence = {
        "portfolio": [
            {key: holding.get(key) for key in ("ticker", "quantity", "avg_buy_price", "sector")}
            for holding in active
        ],
        "invested_cost": total_cost,
        "sector_weights": portfolio["sector_weights"],
        "proposal": details,
    }
    system_message = (
        "Provide an advisory risk assessment for a proposed trade. "
        "Use only the supplied portfolio and simulated position weight. "
        "Explain concentration or diversification changes without inventing facts, current rules, or tax rates. "
        "Return valid JSON with allowed (boolean), risk_level (LOW, MEDIUM, or HIGH), "
        "reasoning, warnings (array), suggested_action (PROCEED, PROCEED_WITH_CAUTION, REDUCE_QUANTITY, or CANCEL), "
        "suggested_quantity when applicable, and portfolio_impact."
    )

    try:
        response = await asyncio.wait_for(
            get_llm().ainvoke([("system", system_message), ("human", json.dumps(evidence, ensure_ascii=False))]),
            timeout=12,
        )
        text = response.content.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:-1]).strip()
        result = json.loads(text)
        if not isinstance(result, dict) or not isinstance(result.get("allowed"), bool):
            raise ValueError("Trade analysis omitted the decision")
        if result.get("risk_level") not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError("Trade analysis omitted the risk level")
        return {**result, **details, "status": "assessed"}
    except Exception:
        return {
            **details,
            "allowed": None,
            "status": "unavailable",
            "risk_level": "UNAVAILABLE",
            "reasoning": "AI trade analysis is temporarily unavailable.",
            "warnings": [],
        }
