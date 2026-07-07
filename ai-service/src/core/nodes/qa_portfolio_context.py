"""QA Portfolio Context node — replaces regulatory RAG for Q&A."""

from __future__ import annotations

from typing import Any

from ..state import PortfolioState


async def build_qa_portfolio_context(state: PortfolioState) -> dict[str, Any]:
    """Build portfolio context specifically for Q&A based on user question."""
    holdings = state.get("normalized_holdings") or state.get("raw_holdings") or []
    errors: list[dict[str, Any]] = list(state.get("errors") or [])

    if not holdings:
        return {
            "qa_context_text": "No portfolio data available.",
            "target_holdings": [],
            "errors": errors,
            "current_node": "qa_portfolio_context"
        }

    # Convert list of Holding or dict to standard list of dict
    source = []
    for h in holdings:
        if isinstance(h, dict):
            source.append({
                "ticker": h.get("ticker", "").strip().upper(),
                "name": h.get("name", h.get("ticker", "")),
                "quantity": float(h.get("quantity") or 0.0),
                "avg_buy_price": float(h.get("avg_buy_price") or h.get("avgBuyPrice") or 0.0),
                "sector": h.get("sector") or "Unknown",
                "status": h.get("status") or ("REALIZED" if float(h.get("quantity") or 0) == 0 else "UNREALIZED"),
                "sell_price": h.get("sell_price"),
                "realized_pnl": h.get("realized_pnl")
            })
        else:
            source.append({
                "ticker": h.ticker.strip().upper(),
                "name": h.name,
                "quantity": h.quantity,
                "avg_buy_price": h.avg_buy_price,
                "sector": h.sector or "Unknown",
                "status": h.status or ("REALIZED" if h.quantity == 0 else "UNREALIZED"),
                "sell_price": h.sell_price,
                "realized_pnl": h.realized_pnl
            })

    # Separate active vs realized
    current_holdings = [item for item in source if item.get("status") != "REALIZED" and item.get("quantity", 0) > 0]
    realized_trades = [item for item in source if item.get("status") == "REALIZED" or item.get("quantity", 0) == 0]

    # Calculate VALUE-BASED weights for active holdings
    for h in current_holdings:
        h["value"] = h["quantity"] * h["avg_buy_price"]
    
    total_value = sum(h["value"] for h in current_holdings)
    
    for h in current_holdings:
        h["portfolio_weight"] = (h["value"] / total_value * 100) if total_value > 0 else 0.0

    # Build active context lines
    active_lines = []
    sorted_active = sorted(current_holdings, key=lambda x: x["portfolio_weight"], reverse=True)
    for h in sorted_active:
        active_lines.append(
            f"- {h['ticker']}: {h['quantity']} shares × ₹{h['avg_buy_price']:.2f} = ₹{h['value']:,.2f} "
            f"({h['portfolio_weight']:.1f}% of portfolio)"
        )
    
    # Build realized context lines
    realized_lines = []
    for h in realized_trades:
        sell = h.get("sell_price") or 0.0
        pnl = h.get("realized_pnl") or (sell - h["avg_buy_price"]) * h["quantity"]
        realized_lines.append(
            f"- {h['ticker']}: Sold {h['quantity']} shares, buy price ₹{h['avg_buy_price']:.2f}, sell price ₹{sell:.2f}, Realized P&L ₹{pnl:,.2f}"
        )
    
    top_holding_ticker = "N/A"
    top_holding_weight = 0.0
    if sorted_active:
        top_holding_ticker = sorted_active[0]["ticker"]
        top_holding_weight = sorted_active[0]["portfolio_weight"]

    concentration_level = 'HIGH' if top_holding_weight > 50 else 'MODERATE' if top_holding_weight > 25 else 'LOW'

    context_text = f"""PORTFOLIO HOLDINGS (Active):
{chr(10).join(active_lines) if active_lines else "No active holdings."}

TOTAL PORTFOLIO VALUE (Active): ₹{total_value:,.2f}
TOTAL REALIZED P&L: ₹{sum(t.get('realized_pnl') or 0.0 for t in realized_trades):,.2f}

TOP ACTIVE HOLDING: {top_holding_ticker} at {top_holding_weight:.1f}%
CONCENTRATION: {concentration_level}

TRADE HISTORY (Realized/Sold positions):
{chr(10).join(realized_lines) if realized_lines else "No trade history."}
"""
    
    # Identify which holdings the question is about
    question = state.get("question", "").lower()
    mentioned_tickers = []
    for item in source:
        ticker = item.get("ticker", "").lower()
        name = item.get("name", "").lower()
        if ticker in question or name in question:
            mentioned_tickers.append(item.get("ticker"))

    # If no specific mention, include all active holdings
    target_holdings = mentioned_tickers if mentioned_tickers else [h.get("ticker") for h in sorted_active]

    return {
        "qa_context_text": context_text,
        "target_holdings": target_holdings,
        "errors": errors,
        "current_node": "qa_portfolio_context"
    }
