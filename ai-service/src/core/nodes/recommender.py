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
    system_prompt = "You are a professional SEBI-compliant senior portfolio recommender and investment advisor."
    
    prompt = f"""You are a SEBI-registered investment advisor (AI assistant). Make specific, actionable recommendations for this portfolio based on the identified risks.

PORTFOLIO OVERVIEW:
{portfolio_context_text}

IDENTIFIED RISKS:
{json.dumps(risk_flags, indent=2)}

For EACH holding in the portfolio, recommend an action:
- ticker: The stock/ETF ticker or fund name
- action: "BUY", "HOLD", "TRIM", or "EXIT"
- priority: "HIGH", "MEDIUM", or "LOW"
- reasoning: 1-2 sentences explaining why, including specific quantities/actions if trimming/buying
- citations: ["AI Advisory Assessment"]
- disclaimer: "This is AI-generated analysis, not SEBI-registered investment advice."

For the overall portfolio:
- portfolio_summary: 1-2 sentences portfolio health assessment and key actions
- overall_risk_level: "HIGH", "MEDIUM", or "LOW"

Respond strictly with a valid JSON object matching this schema. Do not add any preamble, conversational text, or markdown code blocks (like ```json).

Example Response:
{{
  "recommendations": [
    {{
      "ticker": "TATACOMM",
      "action": "TRIM",
      "priority": "HIGH",
      "reasoning": "TATACOMM is 76% of portfolio. Trimming 6 shares reduces weight to 28% and improves diversification.",
      "citations": ["AI Advisory Assessment"],
      "disclaimer": "This is AI-generated analysis, not SEBI-registered investment advice."
    }}
  ],
  "portfolio_summary": "Highly concentrated portfolio in TATACOMM. Rebalancing recommended.",
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
