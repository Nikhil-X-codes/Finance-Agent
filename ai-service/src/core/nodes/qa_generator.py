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
    
    # 1. Detect if it is a Portfolio/User Data question
    portfolio_keywords = [
        "my portfolio", "my holding", "should i sell", "should i buy", 
        "should i hold", "diversified", "concentration", "weight", 
        "allocation", "rebalance", "trim", "exit", "add more",
        "which stock", "riskiest", "best performer", "worst", 
        "sector exposure", "pnl", "profit", "loss", "gain",
        "sold", "bought", "trade", "history", "past", "previous", "realized",
        "what did i sell", "what did i buy", "what do i own",
        "my", "mine", "i own", "did i sell", "did i buy", "have i traded",
        "best trade", "worst trade"
    ]
    is_portfolio_question = any(kw in question_lower for kw in portfolio_keywords)
    
    # Check if user mentioned any held stock ticker
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
            
    mentions_held_stock = any(ticker in question_lower for ticker in held_tickers)
    is_portfolio_question = is_portfolio_question or mentions_held_stock

    active_holdings = [item for item in source_dicts if item.get("status") != "REALIZED" and item.get("quantity", 0) > 0]
    realized_trades = [item for item in source_dicts if item.get("status") == "REALIZED" or item.get("quantity", 0) == 0]

    has_portfolio_data = len(active_holdings) > 0 or len(realized_trades) > 0

    # Initialize LLM
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

    # ==========================================
    # ROUTE A: PORTFOLIO QUESTION (Portfolio RAG)
    # ==========================================
    if is_portfolio_question:
        if not has_portfolio_data:
            return {
                "qa_response": "I don't have your portfolio data to answer this. Please upload a statement first.",
                "qa_citations": [],
                "question_type": "portfolio",
                "generated_via": "RULE_BASED",
                "current_node": "qa_generator"
            }
            
        try:
            # 1. Index portfolio dynamically
            await portfolio_rag.index_portfolio(active_holdings, realized_trades)
            
            # 2. Search index
            results = await portfolio_rag.search(question, top_k=3)
            
            if results:
                context_parts = []
                for r in results:
                    context_parts.append(f"[{r['type'].upper()}] {r['content']}")
                doc_context = "\n\n".join(context_parts)
                
                system_prompt = "You are a professional personal portfolio analysis assistant."
                prompt = f"""You are a personal portfolio assistant. Answer the user's question using their portfolio records.

USER RECORDS:
{doc_context}

USER QUESTION: {question}

RULES:
1. Use ONLY the user records provided above. Do NOT make up numbers or guess.
2. Cite specific tickers, prices, quantities, and realized profits/losses in your answer.
3. Be concise and direct (2-3 sentences).
4. If the question asks for details not present in the user records, say "I don't see that in your records."

ANSWER:"""
                
                res = llm_service.generate(prompt=prompt, system_prompt=system_prompt)
                answer = _clean_repetitive_phrases(res.text)
                
                # Format citations to use actual portfolio trade records
                citations = [
                    {
                        "source": f"{r.get('source', 'portfolio_record')} (Score: {r.get('score', 0):.2f})",
                        "docTitle": f"Portfolio {r.get('type', 'record').capitalize()}",
                        "section": r.get("doc_id", "details"),
                        "date": "2026-07-11",
                        "relevantText": r.get("content", "")[:300]
                    }
                    for r in results
                ]
                
                return {
                    "qa_response": answer,
                    "qa_citations": citations,
                    "question_type": "portfolio_rag",
                    "generated_via": "LLM",
                    "current_node": "qa_generator"
                }
        except Exception as e:
            errors.append({
                "code": "PORTFOLIO_RAG_FAILED",
                "message": f"Portfolio RAG search failed: {e}"
            })

        # Fallback to direct context if RAG search is empty or failed
        system_prompt = "You are a professional SEBI-compliant investment and portfolio analysis AI advisor."
        prompt = f"""You are a portfolio analysis AI. Analyze the user's portfolio context and answer their question.

PORTFOLIO DATA:
{portfolio_context}

USER QUESTION: {question}

RULES:
1. Base your answer on the portfolio data provided above.
2. Always mention exact numbers: quantities, prices, weights, values where relevant.
3. If asked about a sold stock, specify its realized P&L.
4. Respond in 2-3 short sentences. Be direct.

ANSWER:"""

        citations = [
            {
                "source": "user_portfolio",
                "docTitle": "Uploaded Statement",
                "section": "Portfolio Holdings",
                "date": "2026-07-06",
                "relevantText": "Calculated value-based weights and holdings from user's uploaded statement or trade log."
            }
        ]
        
        try:
            res = llm_service.generate(prompt=prompt, system_prompt=system_prompt)
            answer = _clean_repetitive_phrases(res.text)
            return {
                "qa_response": answer,
                "qa_citations": citations,
                "question_type": "portfolio",
                "generated_via": "LLM",
                "current_node": "qa_generator"
            }
        except Exception as e:
            errors.append({"code": "PORTFOLIO_QA_FAILED", "message": str(e)})

    # ==========================================
    # ROUTE B: GENERAL KNOWLEDGE QUESTION
    # ==========================================
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

    try:
        res = llm_service.generate(prompt=prompt, system_prompt=system_prompt)
        answer = _clean_repetitive_phrases(res.text)
        return {
            "qa_response": answer,
            "qa_citations": [],
            "question_type": "general",
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
