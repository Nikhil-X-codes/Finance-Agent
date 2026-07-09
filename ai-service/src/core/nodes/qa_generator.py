"""QA Generator node to produce answering text and citations based on portfolio context."""

from __future__ import annotations

import json
from typing import Any

from src.config.settings import settings
from src.services.llm_service import LLMService
from ..state import PortfolioState


def generate_qa_response(state: PortfolioState) -> dict[str, Any]:
    """Generate final Q&A answer using LLM, context, or general knowledge."""
    question = state.get("question", "").strip()
    portfolio_context = state.get("qa_context_text") or state.get("portfolio_context_text") or ""
    holdings = state.get("normalized_holdings") or state.get("raw_holdings") or []
    errors: list[dict[str, Any]] = list(state.get("errors") or [])

    # Step 1: Detect question type
    question_lower = question.lower()
    
    portfolio_keywords = [
        "my portfolio", "my holding", "should i sell", "should i buy", 
        "should i hold", "diversified", "concentration", "weight", 
        "allocation", "rebalance", "trim", "exit", "add more",
        "which stock", "riskiest", "best performer", "worst", 
        "sector exposure", "pnl", "profit", "loss", "gain",
        "my", "mine"
    ]
    
    is_portfolio_question = any(kw in question_lower for kw in portfolio_keywords)
    
    # Check if user mentioned any held stock ticker
    held_tickers = []
    for h in holdings:
        if isinstance(h, dict):
            ticker = h.get("ticker", "")
        else:
            ticker = getattr(h, "ticker", "")
        if ticker:
            held_tickers.append(ticker.lower())
            
    mentions_held_stock = any(ticker in question_lower for ticker in held_tickers)
    is_portfolio_question = is_portfolio_question or mentions_held_stock

    has_portfolio_data = portfolio_context and portfolio_context != "No portfolio data available."

    # Step 2: Route prompts or handle no portfolio data case
    if is_portfolio_question:
        if not has_portfolio_data:
            return {
                "qa_response": "I don't have your portfolio data to answer this. Please upload a statement first.",
                "qa_citations": [],
                "question_type": "portfolio",
                "generated_via": "RULE_BASED",
                "current_node": "qa_generator"
            }
        
        # Portfolio Q&A Prompt
        system_prompt = "You are a professional SEBI-compliant investment and portfolio analysis AI advisor."
        prompt = f"""You are a portfolio analysis AI. Analyze the user's portfolio and give SPECIFIC, ACTIONABLE advice.

PORTFOLIO DATA:
{portfolio_context}

USER QUESTION: {question}

RULES:
1. Base your answer on the portfolio data provided above.
2. Always mention exact numbers: quantities, prices, weights, values where relevant.
3. Give a CLEAR recommendation: BUY MORE, HOLD, SELL X shares, or TRIM Y shares.
4. If asking about a stock NOT in the portfolio, say "You don't hold [ticker] in your portfolio" and then provide general guidance if known.
5. Never say "I don't have enough information" or use repetitive starting templates. Analyze with what is present.

Respond in 2-3 short sentences. Be direct."""

    else:
        # General Knowledge Prompt
        system_prompt = "You are a helpful financial education assistant."
        prompt = f"""You are a helpful financial education assistant. Answer the user's question clearly and educationally.

USER QUESTION: {question}

RULES:
1. Give a clear, educational answer.
2. Use simple language, avoid excessive jargon, and explain concepts simply.
3. Provide examples where helpful.
4. Keep the answer concise (2-4 sentences).
5. If the question is about investing strategy, mention that it's general advice and not personalized.

Respond in 2-4 sentences. Be direct."""

    # Q&A citations source metadata (only relevant for portfolio context)
    citations = [
        {
            "source": "user_portfolio",
            "docTitle": "Uploaded Statement",
            "section": "Portfolio Holdings",
            "date": "2026-07-06",
            "relevantText": "Calculated value-based weights and holdings from user's uploaded statement or trade log."
        }
    ] if is_portfolio_question else []

    # If Groq key is not configured, run fallback
    if not settings.groq_api_key:
        return {
            "qa_response": render_fallback_response(question, portfolio_context if has_portfolio_data else "No portfolio data available."),
            "qa_citations": citations,
            "question_type": "portfolio" if is_portfolio_question else "general",
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
            "qa_response": render_fallback_response(question, portfolio_context if has_portfolio_data else "No portfolio data available."),
            "qa_citations": citations,
            "question_type": "portfolio" if is_portfolio_question else "general",
            "generated_via": "RULE_BASED",
            "errors": errors,
            "current_node": "qa_generator"
        }

    try:
        res = llm_service.generate(prompt=prompt, system_prompt=system_prompt)
        if res.generated_via == "LLM":
            # Post-process answer to clean repetitive phrases
            answer = _clean_repetitive_phrases(res.text)
            return {
                "qa_response": answer,
                "qa_citations": citations,
                "question_type": "portfolio" if is_portfolio_question else "general",
                "generated_via": "LLM",
                "current_node": "qa_generator"
            }
        else:
            return {
                "qa_response": render_fallback_response(question, portfolio_context if has_portfolio_data else "No portfolio data available."),
                "qa_citations": citations,
                "question_type": "portfolio" if is_portfolio_question else "general",
                "generated_via": "RULE_BASED",
                "current_node": "qa_generator"
            }
    except Exception as e:
        errors.append({
            "code": "QA_LLM_GENERATION_FAILED",
            "message": f"QA LLM generation failed: {e}"
        })
        return {
            "qa_response": render_fallback_response(question, portfolio_context if has_portfolio_data else "No portfolio data available."),
            "qa_citations": citations,
            "question_type": "portfolio" if is_portfolio_question else "general",
            "generated_via": "RULE_BASED",
            "errors": errors,
            "current_node": "qa_generator"
        }


def _clean_repetitive_phrases(text: str) -> str:
    """Remove common repetitive LLM phrases."""
    phrases_to_remove = [
        "Based on the provided portfolio data, ",
        "Based on your portfolio, ",
        "According to the portfolio information, ",
        "As per your holdings, ",
        "I do not have enough information to make a recommendation. However, ",
        "I do not have enough information. However, ",
        "I don't have enough information, but ",
        "Based on the data provided, ",
        "According to the information given, ",
        "Based on the portfolio data, ",
    ]
    
    for phrase in phrases_to_remove:
        text = text.replace(phrase, "")
        text = text.replace(phrase.capitalize(), "")
    
    # Remove double spaces
    text = " ".join(text.split())
    
    # Fix sentences that start with "However," after removal
    text = text.replace(". However, ", ". ")
    text = text.replace(". However ", ". ")
    
    return text.strip()


def render_fallback_response(question: str, portfolio_context: str) -> str:
    """Fallback text generator when LLM is unavailable."""
    return (
        "I am currently operating in fallback mode (AI generation unavailable). Here is a summary of your portfolio details:\n\n"
        f"```\n{portfolio_context}\n```\n\n"
        f"Regarding your question: \"{question}\", please consult an advisor directly."
    )
