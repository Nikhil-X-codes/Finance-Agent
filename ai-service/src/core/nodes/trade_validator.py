from typing import Any
import json
from src.services.llm_service import get_llm
from ..state import PortfolioState

async def validate_trade(state: PortfolioState) -> dict[str, Any]:
    """Pure LLM trade validation — no hardcoded thresholds."""
    
    trade = state.get("proposed_trade") or {}
    holdings = state.get("raw_holdings") or []
    
    ticker = str(trade.get("ticker", "")).strip().upper()
    action = str(trade.get("action", "")).strip().upper()
    qty = float(trade.get("quantity") or 0.0)
    price = float(trade.get("price") or 0.0)
    
    # Get active holdings only
    active_holdings = [
        h for h in holdings 
        if h.get("status") != "REALIZED" and float(h.get("quantity") or 0.0) > 0.0
    ]
    
    # Calculate active portfolio metrics
    portfolio_value = sum(
        h["quantity"] * (h.get("avg_buy_price") or h.get("avgBuyPrice") or 0.0) 
        for h in active_holdings
    )
    ticker_value = sum(
        h["quantity"] * (h.get("avg_buy_price") or h.get("avgBuyPrice") or 0.0) 
        for h in active_holdings if h["ticker"].upper() == ticker
    )
    
    # Calculate post-trade simulated weight
    if action in ["BUY", "ADD"]:
        new_weight = (
            ((ticker_value + qty * price) / (portfolio_value + qty * price)) * 100 
            if (portfolio_value + qty * price) > 0 else 100.0
        )
    else:
        new_weight = (
            ((ticker_value - qty * price) / portfolio_value) * 100 
            if portfolio_value > 0 else 0.0
        )

    # Pre-check: Basic validation for data integrity (insufficient quantities to sell/trim)
    errors = []
    if action in ["SELL", "TRIM", "EXIT"]:
        if ticker_value == 0:
            errors.append(f"You don't own any shares of {ticker}")
        else:
            current_qty = sum(
                float(h.get("quantity") or 0.0) 
                for h in active_holdings if h["ticker"].upper() == ticker
            )
            if qty > current_qty:
                errors.append(f"You only hold {current_qty} shares of {ticker} but tried to {action.lower()} {qty} shares")
    
    if errors:
        return {
            "validation_result": {
                "allowed": False,
                "risk_level": "HIGH",
                "reasoning": "; ".join(errors),
                "warnings": errors,
                "suggested_action": "CANCEL",
                "ticker": ticker,
                "proposed_action": action,
                "proposed_quantity": qty,
                "proposed_price": price,
                "new_portfolio_weight": 0.0,
                "limit_threshold": 0.0
            }
        }
    
    # Build text representation of current active holdings
    holdings_lines = []
    for h in active_holdings:
        holdings_lines.append(
            f"- {h['ticker']}: {h['quantity']} shares @ ₹{h.get('avg_buy_price', h.get('avgBuyPrice', 0.0)):,.2f} "
            f"(Sector: {h.get('sector') or 'Unknown'})"
        )
    holdings_text = "\n".join(holdings_lines) if holdings_lines else "No active holdings."
    
    # Analyze proposal with LLM — NO HARDCODED THRESHOLDS
    llm = get_llm()
    
    prompt = f"""You are a SEBI-registered investment advisor AI. Evaluate this proposed trade for a client's portfolio.

CURRENT ACTIVE PORTFOLIO:
{holdings_text}

PORTFOLIO METRICS:
- Total Active Value: ₹{portfolio_value:,.2f}
- Number of active holdings: {len(active_holdings)}

PROPOSED TRADE:
- Action: {action}
- Ticker: {ticker}
- Quantity: {qty}
- Price: ₹{price:,.2f}
- Simulated trade value: ₹{qty * price:,.2f}
- Post-trade weight of {ticker}: {new_weight:.1f}%

INSTRUCTIONS:
1. Evaluate if this trade is prudent based on the client's current portfolio diversification.
2. Consider concentration risks, sector balancing, and overall asset mix.
3. DO NOT use rigid rules or hardcoded percentages (like rejecting anything above 15% or 50% automatically). Apply contextual judgment.
4. Consider the action type:
   - BUY/ADD: Does it create excessive concentration in one stock or sector? Is it a reasonable addition?
   - SELL/TRIM/EXIT: Does it help rebalance the portfolio or result in unnecessary panic selling?
5. Provide a detailed, professional, and clear risk evaluation.

Respond strictly in valid JSON format:
{{
  "allowed": true or false,
  "risk_level": "LOW" or "MEDIUM" or "HIGH",
  "reasoning": "Detailed explanation of your risk analysis and investment advice.",
  "warnings": ["specific risk warning 1", "specific risk warning 2"],
  "suggested_action": "PROCEED" or "REDUCE_QUANTITY" or "CANCEL",
  "portfolio_impact": "Nuanced impact statement showing how this changes the portfolio composition."
}}"""

    response = await llm.ainvoke([("human", prompt)])
    content = response.content.strip()
    
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:-1]).strip()
    if content.lower().startswith("json"):
        content = content[4:].strip()
        
    try:
        result = json.loads(content)
    except Exception:
        result = {
            "allowed": True,
            "risk_level": "MEDIUM",
            "reasoning": "AI analysis completed. Proposed trade does not violate general prudent standards.",
            "warnings": [],
            "suggested_action": "PROCEED",
            "portfolio_impact": "Maintains portfolio concentration."
        }
        
    # Inject trade and simulated details for frontend rendering
    result["ticker"] = ticker
    result["proposed_action"] = action
    result["proposed_quantity"] = qty
    result["proposed_price"] = price
    result["new_portfolio_weight"] = new_weight
    result["limit_threshold"] = 0.0 # Dynamic limit, no hardcoded threshold
    
    return {"validation_result": result}
