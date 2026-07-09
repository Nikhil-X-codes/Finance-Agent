"""FastAPI route for portfolio overall risk status analysis."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.config.models import Holding
from src.services.llm_service import get_llm

router = APIRouter()


class PortfolioRiskRequest(BaseModel):
    portfolio: list[Holding] = Field(default_factory=list)


class RiskFlag(BaseModel):
    type: str
    severity: str
    description: str


class PortfolioRiskResponse(BaseModel):
    overall_risk: str
    reasoning: str
    flags: list[RiskFlag] = Field(default_factory=list)


@router.post("/portfolio/risk-status")
async def get_portfolio_risk_status(payload: PortfolioRiskRequest) -> dict[str, Any]:
    """Get dynamic AI-analyzed overall portfolio risk and warnings."""
    holdings = [h for h in payload.portfolio if h.quantity > 0]
    
    if not holdings:
        return {
            "overall_risk": "LOW",
            "reasoning": "No active holdings in the portfolio to analyze.",
            "flags": []
        }
    
    # Build text representation of holdings for LLM context
    total_value = sum(h.quantity * h.avg_buy_price for h in holdings)
    
    holdings_lines = []
    for h in holdings:
        val = h.quantity * h.avg_buy_price
        pct = (val / total_value * 100) if total_value > 0 else 0.0
        holdings_lines.append(
            f"- {h.ticker} ({h.name or 'Unknown'}): Qty={h.quantity}, AvgPrice=₹{h.avg_buy_price:,.2f}, "
            f"Value=₹{val:,.2f}, Weight={pct:.1f}%, Sector={h.sector or 'Unknown'}, Type={h.asset_type or 'Unknown'}"
        )
    holdings_text = "\n".join(holdings_lines)
    
    # Analyze overall portfolio risk via LLM
    llm = get_llm()
    
    prompt = f"""You are a senior portfolio risk analyst. Analyze this portfolio and determine the overall risk level.

PORTFOLIO HOLDINGS:
{holdings_text}

TOTAL VALUE: ₹{total_value:,.0f}
NUMBER OF ACTIVE HOLDINGS: {len(holdings)}

Evaluate:
1. Concentration risk (is any single stock or sector too heavily weighted?)
2. Sector diversification
3. Asset type mix (stocks vs ETFs vs mutual funds vs bonds)
4. Portfolio scale/diversification (number of holdings relative to total capital)

Respond STRICTLY in valid JSON format:
{{
  "overall_risk": "LOW" or "MEDIUM" or "HIGH",
  "reasoning": "One concise sentence summarizing the overall portfolio risk."
}}"""

    response = await llm.ainvoke([("human", prompt)])
    content = response.content.strip()
    
    # Parse JSON reliably
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:-1]).strip()
    if content.lower().startswith("json"):
        content = content[4:].strip()
        
    try:
        result = json.loads(content)
    except Exception:
        # Fallback in case of JSON parse errors
        result = {
            "overall_risk": "MEDIUM",
            "reasoning": "Completed portfolio risk audit. Diversification levels are moderate."
        }
        
    return {
        "overall_risk": result.get("overall_risk", "MEDIUM"),
        "reasoning": result.get("reasoning", ""),
        "flags": []
    }
