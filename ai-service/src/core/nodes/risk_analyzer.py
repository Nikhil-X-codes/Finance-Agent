"""Risk Analyzer node for dynamic AI-driven risk analysis."""

from __future__ import annotations

import json
from typing import Any

from src.config.settings import settings
from src.services.llm_service import LLMService
from ..state import PortfolioState


def analyze_portfolio_risk(state: PortfolioState) -> dict[str, Any]:
    """Identify risk flags in holdings using LLM analysis."""
    portfolio_context_text = state.get("portfolio_context_text") or "No portfolio holdings available."
    errors: list[dict[str, Any]] = list(state.get("errors") or [])

    # Default fallback risk flags
    default_flags = []

    # If Groq key is not configured, run rule-based/default fallback
    if not settings.groq_api_key:
        return {
            "risk_flags": default_flags,
            "current_node": "risk_analyzer"
        }

    # Initialize LLM
    try:
        llm_service = LLMService.get_instance()
    except Exception as e:
        errors.append({
            "code": "RISK_LLM_INIT_FAILED",
            "message": f"Risk LLM initialization failed: {e}"
        })
        return {
            "risk_flags": default_flags,
            "errors": errors,
            "current_node": "risk_analyzer"
        }

    # Build prompt for AI risk analysis
    system_prompt = "You are a professional SEBI-compliant senior portfolio risk analyst."
    
    prompt = f"""Analyze this portfolio and identify all financial, diversification, asset mix, and concentration risks.

{portfolio_context_text}

For each risk found, output a JSON list of risk flags.
For each risk flag, include exactly:
- ticker: The stock/ETF ticker or fund name (or "PORTFOLIO" for overall portfolio risks)
- flag_type: The type of risk (e.g., "HIGH_SINGLE_STOCK_CONCENTRATION", "HIGH_SECTOR_CONCENTRATION", "LOW_DIVERSIFICATION", "HIGH_EXPENSE_RATIO", "ADVERSE_NEWS_SENTIMENT")
- severity: "HIGH", "MEDIUM", or "LOW"
- portfolio_weight: The percentage weight of this holding in the portfolio as a decimal fraction (e.g. 0.768 for 76.8% - compute as value / total_value)
- evidence_text: 1 sentence explaining the risk clearly
- citation: "AI Risk Assessment"

Respond strictly with a valid JSON array of objects. Do not add any preamble, conversational text, or markdown code blocks (like ```json).

Example Response:
[
  {{
    "ticker": "TATACOMM",
    "flag_type": "HIGH_SINGLE_STOCK_CONCENTRATION",
    "severity": "HIGH",
    "portfolio_weight": 0.768,
    "evidence_text": "TATACOMM represents 76.8% of the portfolio, which represents a severe concentration risk.",
    "citation": "AI Risk Assessment"
  }}
]"""

    try:
        res = llm_service.generate(prompt=prompt, system_prompt=system_prompt)
        if res.generated_via == "LLM":
            clean_text = res.text.strip()
            if "```json" in clean_text:
                clean_text = clean_text.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_text:
                clean_text = clean_text.split("```")[1].split("```")[0].strip()
            
            risk_flags = json.loads(clean_text)
            
            # Ensure elements are formatted correctly
            formatted_flags = []
            for f in risk_flags:
                if isinstance(f, dict):
                    formatted_flags.append({
                        "ticker": str(f.get("ticker", "PORTFOLIO")),
                        "flag_type": str(f.get("flag_type", "OTHER_RISK")),
                        "severity": str(f.get("severity", "MEDIUM")).upper(),
                        "portfolio_weight": float(f.get("portfolio_weight") or 0.0),
                        "evidence_text": str(f.get("evidence_text", "")),
                        "citation": str(f.get("citation", "AI Risk Assessment"))
                    })
            
            return {
                "risk_flags": formatted_flags,
                "current_node": "risk_analyzer"
            }
        else:
            return {
                "risk_flags": default_flags,
                "current_node": "risk_analyzer"
            }
    except Exception as e:
        errors.append({
            "code": "RISK_LLM_GENERATION_FAILED",
            "message": f"Risk LLM generation or parsing failed: {e}"
        })
        return {
            "risk_flags": default_flags,
            "errors": errors,
            "current_node": "risk_analyzer"
        }
