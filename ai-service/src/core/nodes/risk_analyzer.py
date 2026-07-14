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
    system_prompt = (
        "You are a senior portfolio risk analyst with 15+ years of experience in Indian equity markets "
        "(NSE/BSE). You specialize in retail portfolio risk assessment aligned with SEBI investor "
        "protection guidelines.\n\n"
        "BEHAVIORAL RULES:\n"
        "- Only flag risks that are DIRECTLY supported by the portfolio data provided.\n"
        "- Never fabricate holdings, prices, sectors, or metrics not present in the input.\n"
        "- If the portfolio has fewer than 3 holdings, concentration risk is expected — calibrate severity accordingly.\n"
        "- Express uncertainty clearly rather than guessing when data is ambiguous.\n"
        "- Focus on risks that are ACTIONABLE for a retail investor."
    )
    
    prompt = f"""Analyze the following Indian equity portfolio for risk flags.

PORTFOLIO DATA:
{portfolio_context_text}

ANALYSIS INSTRUCTIONS:
First, mentally walk through these steps before generating output:
1. Examine each holding's weight relative to the total portfolio value.
2. Aggregate sector-level weights and check for sector over-concentration.
3. Assess overall diversification (number of unique holdings, sectors, asset types).
4. Check for any anomalies (e.g., extremely high expense ratios for mutual funds, adverse news).

RISK CATEGORIES TO EVALUATE:
- HIGH_SINGLE_STOCK_CONCENTRATION: A single holding exceeds 40% of portfolio value (HIGH), 20-40% (MEDIUM).
- HIGH_SECTOR_CONCENTRATION: A single sector exceeds 50% of portfolio value (HIGH), 30-50% (MEDIUM).
- LOW_DIVERSIFICATION: Portfolio has fewer than 4 unique active holdings (MEDIUM), or all holdings are in the same sector (HIGH).
- HIGH_EXPENSE_RATIO: Mutual fund TER exceeds 2.25% (MEDIUM), exceeds 2.5% (HIGH).
- ADVERSE_NEWS_SENTIMENT: Holding has negative news signals (severity based on news content).
- SMALL_CAP_OVEREXPOSURE: More than 40% in small-cap stocks without large-cap anchors (MEDIUM).
- NO_DEBT_ALLOCATION: 100% equity with zero debt/hybrid allocation for a multi-holding portfolio (LOW).

SEVERITY GUIDELINES:
- HIGH: Immediate action recommended — risk could cause significant capital loss.
- MEDIUM: Should be addressed during next portfolio review cycle.
- LOW: Only flag if there is a clear, actionable improvement. Do NOT generate LOW flags just to fill the list.

OUTPUT FORMAT:
For each risk found, return a JSON object with exactly these fields:
- "ticker": The stock/ETF ticker or fund name, or "PORTFOLIO" for portfolio-level risks.
- "flag_type": One of the risk categories above.
- "severity": "HIGH", "MEDIUM", or "LOW".
- "portfolio_weight": The holding's weight as a decimal fraction (e.g., 0.768 for 76.8%). Use 0.0 for portfolio-level risks.
- "evidence_text": One clear sentence explaining the risk with specific numbers from the data.
- "citation": "AI Risk Assessment"

IMPORTANT:
- Respond with ONLY a valid JSON array. No preamble, no markdown code blocks, no explanation outside the JSON.
- If no significant risks are found, return an empty array: []
- Every number you cite in evidence_text MUST come from the portfolio data above.

Example:
[
  {{
    "ticker": "TATACOMM",
    "flag_type": "HIGH_SINGLE_STOCK_CONCENTRATION",
    "severity": "HIGH",
    "portfolio_weight": 0.768,
    "evidence_text": "TATACOMM represents 76.8% of the portfolio, far exceeding the 40% single-stock concentration threshold.",
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
