"""Stock discovery and search endpoints."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException, Query
from typing import Any

from src.core.tools.stock_tools import stock_tools
from src.services.market_data import market_data

router = APIRouter()

TICKER = re.compile(r"[A-Z0-9][A-Z0-9&.\-]{0,19}")


def _quote_fields(data: dict) -> dict:
    status = data.get("status")
    if not status:
        if data.get("error") or data.get("current_price") is None:
            status = "unavailable"
        else:
            status = "stale_cache" if data.get("fresh") is False else "published"
    return {
        "price": data.get("current_price"),
        "change": data.get("day_change"),
        "changePercent": data.get("day_change_percent"),
        "source": data.get("source"),
        "fresh": data.get("fresh", status == "published"),
        "marketTimestamp": data.get("timestamp"),
        "quoteStatus": status,
    }


async def _stock_summary(symbol: str, quote: dict, name: str | None = None) -> dict:
    fund = await stock_tools.get_fundamentals(symbol)
    return {
        "symbol": symbol,
        "name": name or quote.get("company_name") or symbol,
        **_quote_fields(quote),
        "pe": fund.data.get("pe"),
        "roe": fund.data.get("roe"),
        "sector": fund.data.get("sector") or "Unknown",
    }


@router.get("/stocks/popular")
async def get_popular_stocks() -> dict[str, Any]:
    if not market_data.enabled:
        return {"status": "disabled", "count": 0, "stocks": []}

    try:
        movers = await market_data.movers(limit=5)
    except Exception as exc:
        raise HTTPException(503, "Market movers are temporarily unavailable.") from exc

    ranked = dict.fromkeys(movers["gainers"] + movers["losers"])
    quotes = await asyncio.gather(*(market_data.quote(symbol) for symbol in ranked))
    by_symbol = dict(zip(ranked, quotes))
    results = [
        {
            "symbol": symbol,
            "name": by_symbol[symbol].get("company_name") or symbol,
            "moverType": direction,
            **_quote_fields(by_symbol[symbol]),
        }
        for direction, symbols in movers.items()
        for symbol in symbols
    ]
    return {"status": "available", "count": len(results), "stocks": results}


@router.get("/stocks/search")
async def search_stocks(q: str = Query(..., min_length=1, max_length=100)) -> dict[str, Any]:
    if not market_data.enabled:
        return {"status": "disabled", "query": q, "results": [], "count": 0}

    query = q.strip().upper()
    if not query:
        raise HTTPException(422, "Enter a stock ticker.")
    exact_quote = await market_data.quote(query) if TICKER.fullmatch(query) else None
    if exact_quote and exact_quote.get("current_price") is not None:
        rows = [await _stock_summary(query, exact_quote)]
        rows[0]["matchType"] = "EXACT_SYMBOL"
    else:
        try:
            matches = await market_data.search(query)
        except Exception as exc:
            raise HTTPException(503, "Stock symbol search is temporarily unavailable.") from exc

        async def summary(match: dict) -> dict:
            symbol = match["symbol"]
            quote = exact_quote if symbol == query and exact_quote is not None else await market_data.quote(symbol)
            name = match["name"] if match["name"] != symbol else None
            return {**(await _stock_summary(symbol, quote, name)), "matchType": "NAME_SEARCH"}

        rows = await asyncio.gather(*(summary(match) for match in matches))

    return {"status": "available", "query": q, "results": rows, "count": len(rows)}


@router.get("/stocks/{symbol}")
async def get_stock_detail(symbol: str) -> dict[str, Any]:
    """Get full details for a single stock."""
    ticker = symbol.upper().strip()
    
    try:
        if not TICKER.fullmatch(ticker):
            raise HTTPException(404, "Unsupported stock symbol.")
        quote, fund, history = await asyncio.gather(
            market_data.quote(ticker), stock_tools.get_fundamentals(ticker), market_data.history(ticker),
        )
        if quote.get("status") == "unsupported" and history.get("status") == "unsupported":
            raise HTTPException(404, "The market-data provider has no data for this symbol.")
        fields = _quote_fields(quote)

        return {
            "symbol": ticker,
            "name": quote.get("company_name") or ticker,
            "price": {
                "current": fields["price"],
                "previousClose": quote.get("previous_close"),
                "change": fields["change"],
                "changePercent": fields["changePercent"],
                "fiftyTwoWeekRange": quote.get("fifty_two_week_range"),
            },
            "fundamentals": {
                "pe": fund.data.get("pe"),
                "pb": fund.data.get("pb"),
                "roe": fund.data.get("roe"),
                "roce": fund.data.get("roce"),
                "debtToEquity": fund.data.get("debt_to_equity"),
                "dividendYield": fund.data.get("dividend_yield"),
                "eps": fund.data.get("eps"),
            },
            "sector": fund.data.get("sector") or "Unknown",
            "source": {
                "price": fields["source"],
                "fundamentals": fund.data.get("source"),
            },
            "fresh": fields["fresh"],
            "marketTimestamp": fields["marketTimestamp"],
            "quoteStatus": fields["quoteStatus"],
            "history": history,
        }
        
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Stock data is temporarily unavailable.") from exc
