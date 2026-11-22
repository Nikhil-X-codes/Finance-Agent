"""Retrieve exactly the records supported by the parsed question."""

import asyncio
import json
import math

from langgraph.runtime import Runtime

from ..qa_types import Evidence, QAProviders, QAState
from src.services.portfolio_facts import summarize_portfolio


def _holding_evidence(row: dict, position: int) -> Evidence:
    ticker = row["ticker"]
    when = row.get("sell_date") if row.get("status") == "REALIZED" else row.get("price_as_of")
    fields = (
        "ticker", "name", "isin", "quantity", "avg_buy_price", "current_price", "price_source",
        "price_as_of", "status", "invested_cost", "market_value", "buy_date", "sell_date",
        "sell_price", "realized_pnl", "sector", "asset_type",
    )
    return {
        "id": f"portfolio:{position}:{ticker}",
        "kind": "portfolio",
        "source": "Confirmed portfolio and trade ledger",
        "title": f"{ticker} account record",
        "date": when,
        "text": json.dumps({key: row.get(key) for key in fields}, ensure_ascii=False),
    }


async def retrieve_portfolio(state: QAState) -> dict:
    query = state["parsed_question"]
    holdings = state.get("raw_holdings") or []
    limitations = list(state.get("limitations") or [])
    if not holdings:
        return {"evidence": [], "limitations": [*limitations, "No confirmed holdings or trade records are available."]}

    matches = {s: False for s in query.symbols}
    evidence = []
    for index, row in enumerate(holdings):
        identifiers = {str(row.get("ticker") or "").upper(), str(row.get("isin") or "").upper()}
        matched = identifiers.intersection(matches)
        for key in matched:
            matches[key] = True
        if matched:
            evidence.append(_holding_evidence(row, index))

    if matches:
        missing = [s for s, present in matches.items() if not present]
        if missing:
            limitations.append(f"No record for {', '.join(missing)} was found in the confirmed portfolio.")
        if len(evidence) > 12:
            limitations.append("The evidence includes the first 12 matching records. Narrow the question for a complete trade breakdown.")
        return {"evidence": evidence[:12], "limitations": limitations}

    figures = summarize_portfolio(holdings)
    summary_doc: Evidence = {
        "id": "portfolio:summary",
        "kind": "portfolio",
        "source": "Calculated portfolio totals",
        "title": "Portfolio totals",
        "date": None,
        "text": json.dumps(figures, ensure_ascii=False),
    }
    evidence = [summary_doc]
    if query.answer_kind == "portfolio_value":
        return {"evidence": evidence, "limitations": limitations}
    evidence.extend(_holding_evidence(row, i) for i, row in enumerate(holdings[:10]))
    if len(holdings) > 10:
        limitations.append("Only the first 10 records are included alongside the totals. Name a symbol for a detailed breakdown.")
    return {"evidence": evidence, "limitations": limitations}


async def retrieve_market(state: QAState, runtime: Runtime[QAProviders]) -> dict:
    parsed = state["parsed_question"]
    evidence = list(state.get("evidence") or [])
    limitations = list(state.get("limitations") or [])
    if parsed.answer_kind == "unsupported_market_analysis":
        return {
            "evidence": evidence,
            "limitations": [
                *limitations,
                "Market Q&A supports the latest quote or the close on one exact date. "
                "Historical series, moving averages, and corporate-action lists are unavailable in chat. "
                "The Stocks page has daily price history when market data is enabled.",
            ],
        }
    if not parsed.symbols:
        return {"evidence": evidence, "limitations": [*limitations, "A stock symbol is needed for the market quote."]}

    async def fetch(symbol: str):
        try:
            return await asyncio.wait_for(runtime.context.market(symbol, parsed.trading_date), timeout=12)
        except Exception:
            return {}

    quotes = await asyncio.gather(*(fetch(symbol) for symbol in parsed.symbols))
    for symbol, quote in zip(parsed.symbols, quotes):
        price = quote.get("current_price")
        timestamp = quote.get("timestamp")
        if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0 or not timestamp:
            limitations.append(f"A dated market price for {symbol} is unavailable.")
            continue
        as_of = str(timestamp)
        if parsed.trading_date and as_of[:10] != parsed.trading_date.isoformat():
            limitations.append(f"No closing price was available for {symbol} on {parsed.trading_date}.")
            continue
        source = str(quote.get("source") or "Market data")
        older = quote.get("fresh") is False
        if older and not parsed.trading_date:
            limitations.append(f"The latest available {symbol} quote is from {as_of}.")
        evidence.append({
            "id": f"market:{symbol}:{as_of}", "kind": "market", "source": source,
            "title": f"{symbol} market price", "date": as_of,
            "text": json.dumps({"symbol": symbol, "price": price, "currency": quote.get("currency", "INR"),
                                "published_at": as_of, "source": source, "latest_session_only": older}),
        })
    return {"evidence": evidence, "limitations": limitations}
