"""Portfolio Context Builder node — replaces regulatory RAG retriever."""

from __future__ import annotations

from typing import Any

from ..state import PortfolioState


async def build_portfolio_context(state: PortfolioState) -> dict[str, Any]:
    """Build rich text context from portfolio holdings for LLM reasoning."""
    holdings = state.get("normalized_holdings") or []
    enriched = state.get("enriched_holdings") or []
    errors: list[dict[str, str]] = list(state.get("errors") or [])

    if not holdings and not enriched:
        return {
            "portfolio_context_text": "No portfolio holdings available.",
            "portfolio_summary": {},
            "errors": errors,
            "current_node": "portfolio_context"
        }

    # Use enriched if available, else raw holdings
    source = enriched if enriched else [
        {
            "ticker": h.ticker,
            "name": h.name,
            "quantity": h.quantity,
            "avg_buy_price": h.avg_buy_price,
            "asset_type": h.asset_type,
            "sector": h.sector or "Unknown",
            "current_price": h.avg_buy_price,  # fallback
            "status": h.status or "UNREALIZED",
            "sell_price": h.sell_price,
            "realized_pnl": h.realized_pnl,
        }
        for h in holdings
    ]

    # Separate current active holdings vs. realized (sold) trades
    current_holdings = [item for item in source if item.get("status") != "REALIZED" and item.get("quantity", 0) > 0]
    realized_trades = [item for item in source if item.get("status") == "REALIZED" or item.get("quantity", 0) == 0]

    # Calculate VALUE-BASED weights for active holdings
    for item in current_holdings:
        item["value"] = item["quantity"] * item["avg_buy_price"]

    total_value = sum(item["value"] for item in current_holdings)

    for item in current_holdings:
        item["portfolio_weight"] = (item["value"] / total_value) if total_value > 0 else 0.0

    for item in realized_trades:
        item["value"] = 0.0
        item["portfolio_weight"] = 0.0

    # Sector breakdown (active holdings only)
    sector_weights: dict[str, float] = {}
    for item in current_holdings:
        sector = item.get("sector") or "Unknown"
        sector_weights[sector] = sector_weights.get(sector, 0.0) + item["value"]

    # Stock-level details for active holdings
    stock_lines = []
    for item in sorted(current_holdings, key=lambda x: x.get("portfolio_weight", 0.0), reverse=True):
        ticker = item.get("ticker", "Unknown")
        name = item.get("name", ticker)
        qty = item.get("quantity", 0)
        avg = item.get("avg_buy_price", 0)
        current = item.get("current_price", avg)
        weight = item.get("portfolio_weight", 0.0) * 100
        pnl = (current - avg) * qty
        pnl_pct = ((current - avg) / avg * 100) if avg > 0 else 0
        
        stock_lines.append(
            f"- {ticker} ({name}): {qty} shares, avg ₹{avg:.2f}, current ₹{current:.2f}, "
            f"weight {weight:.1f}%, P&L ₹{pnl:,.2f} ({pnl_pct:+.1f}%)"
        )

    # Realized details
    realized_lines = []
    for item in realized_trades:
        ticker = item.get("ticker", "Unknown")
        name = item.get("name", ticker)
        qty = item.get("quantity", 0)
        avg = item.get("avg_buy_price", 0)
        sell = item.get("sell_price", 0)
        pnl = item.get("realized_pnl", (sell - avg) * qty)
        pnl_pct = ((sell - avg) / avg * 100) if avg > 0 else 0
        
        realized_lines.append(
            f"- {ticker} ({name}): Sold {qty} shares, avg buy ₹{avg:.2f}, sold ₹{sell:.2f}, Realized P&L ₹{pnl:,.2f} ({pnl_pct:+.1f}%)"
        )

    # Concentration Analysis
    largest_holding_ticker = "N/A"
    largest_holding_weight = 0.0
    if current_holdings:
        largest_holding = max(current_holdings, key=lambda x: x.get("portfolio_weight", 0.0))
        largest_holding_ticker = largest_holding.get("ticker", "N/A")
        largest_holding_weight = largest_holding.get("portfolio_weight", 0.0) * 100

    top_3_weight = sum(sorted((item.get("portfolio_weight", 0.0) for item in current_holdings), reverse=True)[:3]) * 100
    concentration_level = 'HIGH' if largest_holding_weight > 50 else 'MODERATE' if largest_holding_weight > 25 else 'LOW'

    # Build context text
    context_text = f"""PORTFOLIO OVERVIEW (Active):
Total Invested (Active): ₹{total_value:,.2f}
Current Value (Active): ₹{total_value:,.2f}
Unrealized P&L: ₹0.00
Realized P&L (Locked-in): ₹{sum(t.get('realized_pnl', 0.0) for t in realized_trades):,.2f}

SECTOR ALLOCATION (Active Holdings):
{chr(10).join(f"- {sector}: ₹{val:,.2f} ({(val / total_value * 100) if total_value > 0 else 0:.1f}%)" for sector, val in sorted(sector_weights.items(), key=lambda x: x[1], reverse=True))}

ACTIVE HOLDINGS (sorted by weight):
{chr(10).join(stock_lines) if stock_lines else "No active holdings."}

TRADE HISTORY (Realized/Sold positions):
{chr(10).join(realized_lines) if realized_lines else "No trade history."}

CONCENTRATION ANALYSIS (Active Holdings):
- Largest holding: {largest_holding_ticker} at {largest_holding_weight:.1f}%
- Top 3 holdings represent {top_3_weight:.1f}% of active portfolio
- Concentration Level: {concentration_level}
"""

    return {
        "portfolio_context_text": context_text,
        "portfolio_summary": {
            "total_invested": total_value,
            "total_current": total_value,
            "sector_weights": sector_weights,
            "holding_count": len(current_holdings),
            "concentration_level": concentration_level
        },
        "errors": errors,
        "current_node": "portfolio_context"
    }
