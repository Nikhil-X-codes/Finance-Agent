"""QA Generator node to produce answering text and citations using Portfolio RAG or general knowledge."""

from __future__ import annotations

import json
from typing import Any

from src.config.settings import settings
from src.services.llm_service import LLMService, LLMResult
from src.services.portfolio_rag import portfolio_rag
from ..state import PortfolioState
from langsmith import traceable


@traceable(run_type="chain", name="qa_generator_node")
async def generate_qa_response(state: PortfolioState) -> dict[str, Any]:
    """Generate final Q&A answer using Portfolio RAG or general knowledge."""
    question = state.get("question", "").strip()
    portfolio_context = state.get("qa_context_text") or state.get("portfolio_context_text") or ""
    holdings = state.get("normalized_holdings") or state.get("raw_holdings") or []
    errors: list[dict[str, Any]] = list(state.get("errors") or [])

    question_lower = question.lower()

    # Pre-parse holdings and trades
    held_tickers = []
    source_dicts = []
    for h in holdings:
        if isinstance(h, dict):
            ticker = h.get("ticker", "")
            source_dicts.append(h)
        else:
            ticker = getattr(h, "ticker", "")
            source_dicts.append({
                "ticker": h.ticker,
                "name": h.name,
                "quantity": h.quantity,
                "avg_buy_price": h.avg_buy_price,
                "asset_type": h.asset_type,
                "sector": h.sector or "Other",
                "status": h.status or "UNREALIZED",
                "sell_price": h.sell_price or 0.0,
                "realized_pnl": h.realized_pnl or 0.0,
            })
        if ticker:
            held_tickers.append(ticker.lower())

    active_holdings = [item for item in source_dicts if item.get("status") != "REALIZED" and item.get("quantity", 0) > 0]
    realized_trades = [item for item in source_dicts if item.get("status") == "REALIZED" or item.get("quantity", 0) == 0]
    has_portfolio_data = len(active_holdings) > 0 or len(realized_trades) > 0

    # Initialize LLM Service early for classification
    try:
        llm_service = LLMService.get_instance()
    except Exception as e:
        errors.append({
            "code": "QA_LLM_INIT_FAILED",
            "message": f"QA LLM initialization failed: {e}"
        })
        return {
            "qa_response": "AI Service is currently offline. Please consult an advisor directly.",
            "qa_citations": [],
            "question_type": "general",
            "errors": errors,
            "current_node": "qa_generator"
        }

    # Step 1: Pre-classify the question as portfolio-related or general
    is_portfolio_related = False
    if has_portfolio_data:
        classification_system_prompt = (
            "You are a classification assistant. Your task is to classify a user's question about finance "
            "into exactly one of two categories: 'portfolio' or 'general'.\n\n"
            "portfolio: The question is about the user's own investments, holdings, trades, portfolio value, "
            "diversification, risk, sector exposure, P&L, or specific stocks/funds they own/sold (e.g. TATACOMM, GMBREW, etc.).\n"
            "general: The question is a general finance, stock market, investment concept, definition, rule, or taxation query "
            "(e.g., 'what is SIP?', 'how do mutual funds work?', 'what is the rate of STCG in India?', etc.) "
            "that does not reference the user's specific assets or portfolio.\n\n"
            "Output ONLY the category name ('portfolio' or 'general'). Do not output any explanation or extra text."
        )
        classification_prompt = f"Classify this question:\n\"{question}\""
        try:
            class_res = llm_service.generate(prompt=classification_prompt, system_prompt=classification_system_prompt)
            class_text = class_res.text.strip().lower()
            if "portfolio" in class_text:
                is_portfolio_related = True
        except Exception as e:
            # Fallback keyword-based classification on exception
            portfolio_keywords = [
                "my", "portfolio", "holding", "own", "hold", "sell", "buy",
                "profit", "loss", "p&l", "pnl", "diversif", "concentr",
                "weight", "invest", "value", "performance", "return"
            ]
            is_portfolio_related = any(kw in question_lower for kw in portfolio_keywords) or any(t in question_lower for t in held_tickers)

    # Build context and retrieve RAG records only if portfolio-related
    user_context = ""
    citations = []

    if is_portfolio_related:
        try:
            # 1. Index portfolio dynamically (now indexes 8 document types)
            await portfolio_rag.index_portfolio(active_holdings, realized_trades)
            # 2. Retrieve top matching chunks (RAG uses adaptive thresholds internally)
            rag_results = await portfolio_rag.search(question, top_k=5)
            
            if rag_results:
                context_parts = []
                for r in rag_results:
                    doc_type = r['type'].upper()
                    context_parts.append(f"[{doc_type}] {r['content']}")
                    
                    # Map doc types to user-friendly titles
                    type_labels = {
                        "holding": "Portfolio Holding",
                        "trade": "Trade History",
                        "summary": "Portfolio Summary",
                        "analysis": "Portfolio Analysis"
                    }
                    
                    from datetime import date
                    citations.append({
                        "source": f"{r.get('source', 'portfolio')} (Score: {r.get('score', 0):.2f})",
                        "docTitle": type_labels.get(r.get('type', 'record'), "Portfolio Record"),
                        "section": r.get("doc_id", "details"),
                        "date": date.today().isoformat(),
                        "relevantText": r.get("content", "")[:300]
                    })
                user_context += "RELEVANT PORTFOLIO RECORDS:\n" + "\n".join(context_parts) + "\n\n"
        except Exception as e:
            errors.append({"code": "QA_RAG_SEARCH_FAILED", "message": str(e)})

        # Append general summary context
        if portfolio_context and portfolio_context != "No portfolio data available.":
            user_context += f"PORTFOLIO OVERVIEW & SUMMARY:\n{portfolio_context}\n"

    # Generate answer with unified prompt
    system_prompt = (
        "You are a knowledgeable personal portfolio analyst and Indian financial education assistant. "
        "You have dual expertise:\n"
        "1. PORTFOLIO ANALYSIS: You can analyze holdings, calculate returns, assess diversification, and explain "
        "portfolio performance using the user's actual data.\n"
        "2. FINANCIAL EDUCATION: You can explain Indian market concepts (NSE/BSE, SEBI regulations, mutual funds, "
        "STCG/LTCG taxation, SIP strategies, etc.) clearly and accurately.\n\n"
        "BEHAVIORAL RULES:\n"
        "- When answering portfolio questions, ALWAYS cite exact numbers (tickers, quantities, prices, P&L) from the provided data.\n"
        "- Never fabricate holdings, prices, or transactions that are not in the user's data.\n"
        "- If the user asks about a holding not in their portfolio, clearly state: 'I don't see that in your portfolio records.'\n"
        "- For general finance questions, provide accurate information grounded in Indian market context.\n"
        "- If you are not confident about a specific regulation, date, or circular number, say so rather than guessing.\n"
        "- Never start responses with 'Based on your portfolio...' or similar repetitive openings."
    )

    # Build conversation context from history
    conversation_context = ""
    conv_history = state.get("conversation_history") or []
    if conv_history:
        recent_turns = conv_history[-6:]  # Last 3 exchanges (6 messages)
        history_lines = []
        for turn in recent_turns:
            role = turn.get("role", "user").upper()
            content = turn.get("content", "")[:300]
            history_lines.append(f"{role}: {content}")
        conversation_context = "RECENT CONVERSATION:\n" + "\n".join(history_lines) + "\n\n"

    prompt = f"""{conversation_context}USER PORTFOLIO DATA:
{user_context if user_context else "No user portfolio data uploaded yet."}

USER QUESTION: {question}

ANSWER INSTRUCTIONS:
Follow this decision process:

STEP 1 — CLASSIFY THE QUESTION:
Determine if the user is asking about their OWN investments, holdings, trades, portfolio performance, weights, profits/losses, or any specific ticker they hold.

STEP 2 — IF PORTFOLIO-RELATED:
- Use the USER PORTFOLIO DATA above to answer with precision.
- Cite exact tickers, quantities, buy/sell prices, values, weights, and P&L from the data.
- Perform any requested calculations (returns, percentage changes, weight comparisons) using the actual numbers.
- If the question references a holding not in their data, say "I don't see [ticker] in your portfolio records."

STEP 3 — IF GENERAL FINANCE QUESTION:
- Answer as an Indian financial education expert.
- Explain concepts in the context of Indian markets (NSE/BSE, SEBI, INR, Indian tax rules like STCG at 20%, LTCG at 12.5% above ₹1.25 lakh).
- Use concrete examples with INR values when explaining concepts.
- If unsure about a specific regulation or date, acknowledge the uncertainty.

RESPONSE FORMAT:
- Be concise but complete. Use 2-4 sentences for simple questions, more for complex analysis.
- For portfolio questions, always include the specific numbers that support your answer.
- Never start with "Based on your portfolio..." or similar phrases.
- Use plain language — avoid jargon unless the user used it first.

ANSWER:"""

    try:
        res = llm_service.generate(prompt=prompt, system_prompt=system_prompt)
        answer = _clean_repetitive_phrases(res.text)
        
        # Align badge question type with classification and RAG presence
        if is_portfolio_related:
            question_type = "portfolio_rag" if citations else "portfolio"
        else:
            question_type = "general"

        return {
            "qa_response": answer,
            "qa_citations": citations,
            "question_type": question_type,
            "generated_via": "LLM",
            "current_node": "qa_generator"
        }
    except Exception as e:
        return {
            "qa_response": "I'm sorry, I'm unable to process this question right now.",
            "qa_citations": [],
            "question_type": "general",
            "generated_via": "RULE_BASED",
            "errors": errors + [{"code": "GENERAL_QA_FAILED", "message": str(e)}],
            "current_node": "qa_generator"
        }


def _clean_repetitive_phrases(text: str) -> str:
    """Remove common repetitive LLM phrases."""
    phrases_to_remove = [
        "Based on the provided portfolio data, ",
        "Based on your portfolio data, ",
        "Based on your portfolio, ",
        "According to the portfolio information, ",
        "As per your holdings, ",
        "I do not have enough information to make a recommendation. However, ",
        "I do not have enough information. However, ",
        "I don't have enough information, but ",
        "Based on the data provided, ",
        "According to the information given, ",
        "From the records provided, ",
    ]
    
    for phrase in phrases_to_remove:
        text = text.replace(phrase, "")
        text = text.replace(phrase.capitalize(), "")
    
    # Fix double spaces and orphaned transitions
    text = " ".join(text.split())
    text = text.replace(". However, ", ". ")
    text = text.replace(". However ", ". ")
    text = text.replace(". That said, ", ". ")
    
    # Fix: If answer starts with "However," or "That said,"
    if text.lower().startswith("however, "):
        text = text[9:]
    if text.lower().startswith("that said, "):
        text = text[11:]
        
    return text.strip()
