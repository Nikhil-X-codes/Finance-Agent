"""QA Generator node to produce answering text and citations based on portfolio context."""

from __future__ import annotations

from typing import Any

from src.config.settings import settings
from src.services.llm_service import LLMService
from ..state import PortfolioState


def generate_qa_response(state: PortfolioState) -> dict[str, Any]:
    """Generate final Q&A answer using LLM and portfolio context."""
    question = state.get("question", "")
    portfolio_context = state.get("qa_context_text") or state.get("portfolio_context_text") or ""
    errors: list[dict[str, Any]] = list(state.get("errors") or [])

    # Portfolio-derived citations source metadata
    citations = [
        {
            "source": "user_portfolio",
            "docTitle": "Uploaded Statement",
            "section": "Portfolio Holdings",
            "date": "2026-07-06",
            "relevantText": "Calculated value-based weights and holdings from user's uploaded statement or trade log."
        }
    ]

    if not portfolio_context or portfolio_context == "No portfolio data available.":
        return {
            "qa_response": "I don't have your portfolio data to answer this. Please upload a statement first.",
            "qa_citations": [],
            "generated_via": "RULE_BASED",
            "current_node": "qa_generator"
        }

    # If Groq key is not configured, run simple rule-based fallback
    if not settings.groq_api_key:
        return {
            "qa_response": render_fallback_response(question, portfolio_context),
            "qa_citations": citations,
            "generated_via": "RULE_BASED",
            "current_node": "qa_generator"
        }

    # Initialize LLM
    try:
        llm_service = LLMService.get_instance()
    except Exception as e:
        errors.append({
            "code": "QA_LLM_INIT_FAILED",
            "message": f"QA LLM initialization failed: {e}"
        })
        return {
            "qa_response": render_fallback_response(question, portfolio_context),
            "qa_citations": citations,
            "generated_via": "RULE_BASED",
            "errors": errors,
            "current_node": "qa_generator"
        }

    # Build prompt with ONLY portfolio context & actionable rules
    system_prompt = "You are a professional SEBI-compliant investment and portfolio analysis AI advisor."
    
    prompt = f"""You are a portfolio analysis AI. Analyze the user's portfolio and give SPECIFIC, ACTIONABLE advice.

PORTFOLIO DATA:
{portfolio_context}

USER QUESTION: {question}

RULES:
1. Always mention exact numbers: quantities, prices, weights, values
2. Give a CLEAR recommendation: BUY MORE, HOLD, SELL X shares, or TRIM Y shares
3. Explain WHY in one sentence (concentration risk, diversification, sector exposure)
4. If asking about one stock, compare it to portfolio total
5. Never say "I don't have enough information" — you have all the data
6. Calculate: value = quantity × avg_buy_price, weight = value / total_value

Respond in 2-3 short sentences. Be direct."""

    try:
        res = llm_service.generate(prompt=prompt, system_prompt=system_prompt)
        if res.generated_via == "LLM":
            return {
                "qa_response": res.text,
                "qa_citations": citations,
                "generated_via": "LLM",
                "current_node": "qa_generator"
            }
        else:
            return {
                "qa_response": render_fallback_response(question, portfolio_context),
                "qa_citations": citations,
                "generated_via": "RULE_BASED",
                "current_node": "qa_generator"
            }
    except Exception as e:
        errors.append({
            "code": "QA_LLM_GENERATION_FAILED",
            "message": f"QA LLM generation failed: {e}"
        })
        return {
            "qa_response": render_fallback_response(question, portfolio_context),
            "qa_citations": citations,
            "generated_via": "RULE_BASED",
            "errors": errors,
            "current_node": "qa_generator"
        }


def render_fallback_response(question: str, portfolio_context: str) -> str:
    """Fallback text generator when LLM is unavailable."""
    return (
        "I am currently operating in fallback mode (AI generation unavailable). Here is a summary of your portfolio details:\n\n"
        f"```\n{portfolio_context}\n```\n\n"
        f"Regarding your question: \"{question}\", please consult a SEBI-registered advisor directly.\n\n"
        "**Disclaimer:** This is AI-generated research, not SEBI-registered advice."
    )
