"""Stock discovery and search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Any

from src.core.tools.stock_tools import stock_tools

router = APIRouter()

# Top 5 popular Indian stocks
POPULAR_STOCKS = ["RELIANCE", "HDFCBANK", "INFY", "TCS", "ITC"]


@router.get("/stocks/popular")
async def get_popular_stocks() -> dict[str, Any]:
    """Fetch current data for 5 popular stocks."""
    results = []
    
    for symbol in POPULAR_STOCKS:
        try:
            quote = await stock_tools.get_quote(symbol)
            fund = await stock_tools.get_fundamentals(symbol)
            
            results.append({
                "symbol": symbol,
                "name": quote.data.get("company_name") or symbol,
                "price": quote.data.get("current_price"),
                "change": quote.data.get("day_change"),
                "changePercent": quote.data.get("day_change_percent"),
                "pe": fund.data.get("pe"),
                "roe": fund.data.get("roe"),
                "sector": quote.data.get("sector") or fund.data.get("sector") or "Unknown",
                "source": quote.data.get("source", "YAHOO"),
                "fresh": quote.data.get("fresh", True),
            })
        except Exception as e:
            results.append({
                "symbol": symbol,
                "name": symbol,
                "error": str(e),
            })
    
    return {
        "count": len(results),
        "stocks": results
    }


@router.get("/stocks/search")
async def search_stocks(
    q: str = Query(..., min_length=1, description="Search query — name or symbol")
) -> dict[str, Any]:
    """
    Search stocks by name or symbol.
    Tries exact symbol match first, then Yahoo search.
    """
    query = q.strip().upper()
    
    # Try exact symbol match first (fast path)
    try:
        quote = await stock_tools.get_quote(query)
        if quote.data.get("current_price"):
            # It's a valid symbol
            fund = await stock_tools.get_fundamentals(query)
            return {
                "query": q,
                "results": [{
                    "symbol": query,
                    "name": quote.data.get("company_name") or query,
                    "price": quote.data.get("current_price"),
                    "change": quote.data.get("day_change"),
                    "changePercent": quote.data.get("day_change_percent"),
                    "pe": fund.data.get("pe"),
                    "roe": fund.data.get("roe"),
                    "sector": quote.data.get("sector") or fund.data.get("sector") or "Unknown",
                    "matchType": "EXACT_SYMBOL"
                }],
                "count": 1
            }
    except Exception:
        pass
    
    # Fallback: Yahoo search by name
    try:
        search_results = await stock_tools.search_by_name(q)
        if search_results:
            enriched = []
            for r in search_results[:5]:
                symbol = r["symbol"]
                try:
                    quote = await stock_tools.get_quote(symbol)
                    fund = await stock_tools.get_fundamentals(symbol)
                    enriched.append({
                        "symbol": symbol,
                        "name": r.get("name") or quote.data.get("company_name") or symbol,
                        "price": quote.data.get("current_price"),
                        "change": quote.data.get("day_change"),
                        "changePercent": quote.data.get("day_change_percent"),
                        "pe": fund.data.get("pe"),
                        "roe": fund.data.get("roe"),
                        "sector": quote.data.get("sector") or fund.data.get("sector") or "Unknown",
                        "matchType": "NAME_SEARCH"
                    })
                except Exception:
                    enriched.append({
                        "symbol": symbol,
                        "name": r.get("name") or symbol,
                        "matchType": "NAME_SEARCH",
                        "price": None,
                    })
            
            return {
                "query": q,
                "results": enriched,
                "count": len(enriched)
            }
    except Exception as e:
        pass
    
    # Nothing found
    return {
        "query": q,
        "results": [],
        "count": 0,
        "message": f"No stocks found for '{q}'. Try symbols like RELIANCE, HDFCBANK, INFY, TCS, ITC"
    }


@router.get("/stocks/{symbol}")
async def get_stock_detail(symbol: str) -> dict[str, Any]:
    """Get full details for a single stock."""
    ticker = symbol.upper().strip()
    
    try:
        quote = await stock_tools.get_quote(ticker)
        fund = await stock_tools.get_fundamentals(ticker)
        
        if quote.data.get("error") == "QUOTE_UNAVAILABLE":
            raise HTTPException(404, f"Stock {ticker} not found")
        
        return {
            "symbol": ticker,
            "name": quote.data.get("company_name") or ticker,
            "price": {
                "current": quote.data.get("current_price"),
                "previousClose": quote.data.get("previous_close"),
                "change": quote.data.get("day_change"),
                "changePercent": quote.data.get("day_change_percent"),
                "fiftyTwoWeekRange": quote.data.get("fifty_two_week_range"),
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
            "sector": quote.data.get("sector") or fund.data.get("sector") or "Unknown",
            "source": {
                "price": quote.data.get("source", "YAHOO"),
                "fundamentals": fund.data.get("source", "SCREENER")
            },
            "fresh": quote.data.get("fresh", True),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch {ticker}: {str(e)}")
