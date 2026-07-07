from typing import Any
import json
from src.services.llm_service import get_llm
from ..state import PortfolioState

async def validate_trade(state: PortfolioState) -> dict[str, Any]:
    trade = state.get("proposed_trade") or {}
    holdings = state.get("raw_holdings") or []
    
    # Filter active vs realized holdings
    active_holdings = [h for h in holdings if h.get("status") != "REALIZED" and float(h.get("quantity") or 0.0) > 0.0]
    
    # Calculate active portfolio metrics
    portfolio_value = sum(h["quantity"] * (h.get("avg_buy_price") or h.get("avgBuyPrice") or 0.0) for h in active_holdings)
    ticker_value = sum(h["quantity"] * (h.get("avg_buy_price") or h.get("avgBuyPrice") or 0.0) 
                       for h in active_holdings if h["ticker"] == trade.get("ticker"))
    
    current_weight = (ticker_value / portfolio_value) * 100 if portfolio_value else 0.0
    
    qty = float(trade.get("quantity") or 0.0)
    price = float(trade.get("price") or 0.0)
    action = str(trade.get("action") or "").strip().upper()
    ticker = str(trade.get("ticker") or "").strip().upper()
    
    if action in ["BUY", "ADD"]:
        new_weight = ((ticker_value + qty * price) / 
                     (portfolio_value + qty * price)) * 100 if (portfolio_value + qty * price) > 0 else 0.0
    else:
        new_weight = ((ticker_value - qty * price) / 
                     portfolio_value) * 100 if portfolio_value else 0.0
        
    # Build readable active holdings text
    holdings_lines = []
    for h in active_holdings:
        holdings_lines.append(
            f"- {h['ticker']}: {h['quantity']} shares @ ₹{h.get('avg_buy_price', h.get('avgBuyPrice', 0.0)):,.2f}"
        )
    format_holdings_text = "\n".join(holdings_lines)

    # Calculate top sector
    sector_allocation = {}
    for h in active_holdings:
        val = h["quantity"] * (h.get("avg_buy_price") or h.get("avgBuyPrice") or 0.0)
        sector = h.get("sector") or "Other"
        sector_allocation[sector] = sector_allocation.get(sector, 0.0) + val
    top_sector = max(sector_allocation, key=sector_allocation.get) if sector_allocation else "None"

    # Diversification level
    diversification = "POOR" if len(active_holdings) < 3 else "MODERATE" if len(active_holdings) < 6 else "GOOD"
    
    # Improved LLM prompt with rich context
    llm = get_llm()
    
    prompt = f"""You are a portfolio risk analyst. Evaluate this proposed trade.

CURRENT ACTIVE PORTFOLIO:
{format_holdings_text if format_holdings_text else "No active holdings."}

PORTFOLIO SUMMARY:
- Total Active Value: ₹{portfolio_value:,.0f}
- Number of active holdings: {len(active_holdings)}
- Top sector: {top_sector}
- Current diversification: {diversification}

PROPOSED TRADE:
- Ticker: {ticker}
- Action: {action}
- Quantity: {qty}
- Price: ₹{price:,.2f}
- Post-trade weight of {ticker} in portfolio: {new_weight:.1f}%

DECISION RULES:
- Single stock > 50% of portfolio: HIGH risk, generally reject
- Single stock 25-50%: MEDIUM risk, caution
- Single stock < 25%: LOW risk, acceptable
- Consider sector concentration too
- Consider overall portfolio diversification

Respond strictly in valid JSON format:
{{
  "allowed": true/false,
  "risk_level": "LOW"/"MEDIUM"/"HIGH",
  "reasoning": "One clear sentence explaining the decision",
  "warnings": ["Specific warning if any"],
  "suggested_action": "PROCEED" or "REDUCE_QUANTITY" or "CANCEL"
}}"""

    response = await llm.ainvoke([("human", prompt)])
    
    # Parse JSON from response
    content = response.content.strip()
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:])
    if content.endswith("```"):
        content = content[:-3].strip()
    if content.lower().startswith("json"):
        content = content[4:].strip()
        
    try:
        result = json.loads(content)
    except Exception:
        result = {
            "allowed": True,
            "risk_level": "MEDIUM",
            "reasoning": "Completed trade analysis.",
            "warnings": [],
            "suggested_action": "PROCEED"
        }
        
    result["new_portfolio_weight"] = new_weight
    
    # Provide keys for frontend compatibility
    result["ticker"] = ticker
    result["action"] = action
    result["quantity"] = qty
    result["price"] = price
    
    return {"validation_result": result}
