"""Recommender node for structured AI-driven investment recommendations."""

from __future__ import annotations

import json
from typing import Any

from src.config.settings import settings
from src.services.llm_service import LLMService
from ..state import PortfolioState


def generate_recommendations(state: PortfolioState) -> dict[str, Any]:
    """Generate BUY/HOLD/TRIM/EXIT recommendations using LLM and portfolio context."""
    portfolio_context_text = state.get("portfolio_context_text") or "No portfolio holdings available."
    risk_flags = state.get("risk_flags") or []
    errors: list[dict[str, str]] = list(state.get("errors") or [])

    # Default fallback recommendations structure
    default_recs = {
        "recommendations": [],
        "portfolio_summary": "AI recommendations currently unavailable. Please verify API configuration.",
        "overall_risk_level": "LOW",
        "generated_via": "RULE_BASED"
    }

    # If Groq is not configured or empty, immediately use fallback
    if not settings.groq_api_key:
        return {
            "recommendations": default_recs,
            "generated_via": "RULE_BASED",
            "current_node": "recommender"
        }

    # Initialize LLM Service
    try:
        llm_service = LLMService.get_instance()
    except Exception as e:
        errors.append({
            "code": "RECOMMENDER_LLM_INIT_FAILED",
            "message": f"Recommender LLM Service initialization failed: {e}"
        })
        return {
            "recommendations": default_recs,
            "generated_via": "RULE_BASED",
            "errors": errors,
            "current_node": "recommender"
        }

    # Build prompt
    system_prompt = (
        "You are a senior investment advisor with deep expertise in Indian equity and mutual fund markets "
        "(NSE/BSE, AMFI-registered funds). You provide actionable, risk-aware portfolio recommendations "
        "focused on long-term wealth creation and prudent diversification.\n\n"
        "BEHAVIORAL RULES:\n"
        "- Only reference tickers, quantities, prices, and sectors that appear in the provided portfolio data.\n"
        "- Never recommend specific buy prices, target prices, or future price predictions — you do not have real-time market data.\n"
        "- Never fabricate holdings or metrics not present in the input.\n"
        "- TRIM recommendations MUST include a specific quantity to trim and the resulting target weight.\n"
        "- BUY recommendations should focus on what asset classes or sectors to add, not specific stocks to purchase.\n"
        "- Always include the mandatory disclaimer on every recommendation.\n"
        "- If the portfolio has only 1-2 holdings, prioritize diversification above all else."
    )
    
    prompt = f"""Generate specific, actionable recommendations for this portfolio based on the identified risks.

PORTFOLIO OVERVIEW:
{portfolio_context_text}

IDENTIFIED RISKS:
{json.dumps(risk_flags, indent=2)}

ANALYSIS APPROACH — Follow these steps:
1. For each holding, evaluate: current weight → associated risk flags → whether action is needed.
2. For TRIM/EXIT recommendations, calculate the exact quantity to sell to reach a healthier weight.
3. For BUY/HOLD recommendations, explain the strategic rationale (diversification benefit, sector balance, etc.).
4. Assess the portfolio holistically: is it concentrated, sector-skewed, or missing asset classes?

INDIAN MARKET CONSIDERATIONS:
- Holdings held < 12 months are subject to Short-Term Capital Gains (STCG) tax at 20%. Factor this into TRIM/EXIT urgency.
- ELSS mutual funds have a 3-year lock-in period — do NOT recommend EXIT for ELSS within lock-in.
- Mutual funds may have exit loads within 1 year — note this in reasoning if applicable.
- Consider recommending index funds (Nifty 50, Nifty Next 50) as diversification instruments for concentrated portfolios.

ACTION DEFINITIONS:
- BUY: Add new position or increase existing position to improve diversification.
- HOLD: Current position is appropriately sized; no action needed.
- TRIM: Reduce position size — MUST specify exact quantity to sell and target weight percentage.
- EXIT: Fully exit the position — only for holdings with HIGH risk flags or fundamentally compromised positions.

For EACH holding in the portfolio, provide:
- "ticker": The stock/ETF ticker or fund name.
- "action": "BUY", "HOLD", "TRIM", or "EXIT".
- "priority": "HIGH" (act within 1 week), "MEDIUM" (act within 1 month), or "LOW" (next rebalancing cycle).
- "reasoning": 2-3 sentences explaining why, with specific quantities and target weights for TRIM/EXIT actions.
- "citations": ["AI Advisory Assessment"]
- "disclaimer": "This is AI-generated analysis for educational purposes only. Not SEBI-registered investment advice. Consult a qualified financial advisor before acting."

For the overall portfolio:
- "portfolio_summary": 2-3 sentences summarizing portfolio health, key risk, and the single most important action.
- "overall_risk_level": "HIGH", "MEDIUM", or "LOW"

IMPORTANT:
- Respond with ONLY a valid JSON object. No preamble, no markdown code blocks, no explanation outside the JSON.
- Every ticker and number you reference MUST come from the portfolio data above.

Example:
{{
  "recommendations": [
    {{
      "ticker": "TATACOMM",
      "action": "TRIM",
      "priority": "HIGH",
      "reasoning": "TATACOMM is 76.8% of portfolio, creating severe concentration risk. Trim 6 of 10 shares to reduce weight to approximately 28%. Consider STCG tax implications if held under 12 months.",
      "citations": ["AI Advisory Assessment"],
      "disclaimer": "This is AI-generated analysis for educational purposes only. Not SEBI-registered investment advice. Consult a qualified financial advisor before acting."
    }}
  ],
  "portfolio_summary": "Highly concentrated portfolio with 76.8% in a single stock. Immediate rebalancing by trimming TATACOMM and diversifying into 2-3 additional sectors is the top priority.",
  "overall_risk_level": "HIGH"
}}"""

    # Call LLM
    try:
        res = llm_service.generate(prompt=prompt, system_prompt=system_prompt)
        
        if res.generated_via == "LLM":
            clean_text = res.text.strip()
            if "```json" in clean_text:
                clean_text = clean_text.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_text:
                clean_text = clean_text.split("```")[1].split("```")[0].strip()
            
            recommendations_dict = json.loads(clean_text)
            
            # Formulate output structure
            overall_risk = str(recommendations_dict.get("overall_risk_level", "LOW")).upper()
            recs_list = recommendations_dict.get("recommendations", [])
            summary_text = str(recommendations_dict.get("portfolio_summary", ""))
            
            # Format recommendations
            formatted_recs = []
            for r in recs_list:
                if isinstance(r, dict):
                    formatted_recs.append({
                        "ticker": str(r.get("ticker", "PORTFOLIO")),
                        "action": str(r.get("action", "HOLD")).upper(),
                        "priority": str(r.get("priority", "LOW")).upper(),
                        "reasoning": str(r.get("reasoning", "")),
                        "citations": r.get("citations") or ["AI Advisory Assessment"],
                        "disclaimer": str(r.get("disclaimer", "This is AI-generated analysis, not SEBI-registered investment advice."))
                    })
            
            return {
                "recommendations": {
                    "recommendations": formatted_recs,
                    "portfolio_summary": summary_text,
                    "overall_risk_level": overall_risk,
                },
                "generated_via": "LLM",
                "current_node": "recommender"
            }
        else:
            return {
                "recommendations": default_recs,
                "generated_via": "RULE_BASED",
                "current_node": "recommender"
            }
    except Exception as e:
        errors.append({
            "code": "RECOMMENDER_LLM_GENERATION_FAILED",
            "message": f"Recommender LLM generation or JSON parsing failed: {e}."
        })
        return {
            "recommendations": default_recs,
            "generated_via": "RULE_BASED",
            "errors": errors,
            "current_node": "recommender"
        }
