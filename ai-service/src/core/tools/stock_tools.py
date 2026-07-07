"""Stock tools — Yahoo primary (price), Screener primary (fundamentals), search by name."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus

import httpx

from ...config.constants import STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS, STOCK_QUOTE_CACHE_TTL_SECONDS
from ...services.cache_service import cache_service

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?range=5d&interval=1d"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=5&newsCount=0"
SCREENER_URL = "https://www.screener.in/company/{slug}/consolidated/"


class _TagStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.parts.append(cleaned)


def _strip_tags(html: str) -> str:
    parser = _TagStripper()
    parser.feed(html)
    return " ".join(parser.parts)


@dataclass(slots=True)
class StockResult:
    data: dict[str, Any]
    stale: bool = False
    error: str | None = None


class StockTools:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        }
        self._client = httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True)
        return self._client

    @staticmethod
    def _cache_key(prefix: str, symbol: str) -> str:
        return f"{prefix}:{symbol.upper()}"

    @staticmethod
    def _is_fresh(payload: dict[str, Any]) -> bool:
        expires_at = int(payload.get("_cache_expires_at", 0) or 0)
        return expires_at > int(time.time())

    @staticmethod
    def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"_cache_expires_at", "_stale"}}

    @staticmethod
    def _decorate(
        payload: dict[str, Any],
        *,
        cached: bool,
        fresh: bool,
        source: str | None = None,
        stale_warning: str | None = None,
    ) -> dict[str, Any]:
        data = dict(payload)
        data["cached"] = cached
        data["fresh"] = fresh
        if source:
            data["source"] = source
        if stale_warning:
            data["stale_warning"] = stale_warning
        return data

    # ───────────────────────────────────────────────
    # SEARCH BY NAME (NEW)
    # ───────────────────────────────────────────────
    async def search_by_name(self, query: str) -> list[dict[str, Any]]:
        """Search stocks by company name. Returns list of matches."""
        client = await self._get_client()
        url = YAHOO_SEARCH_URL.format(query=quote_plus(query))
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        
        quotes = data.get("quotes", [])
        results = []
        for q in quotes:
            # Only Indian stocks (.NS suffix)
            symbol = q.get("symbol", "")
            if not symbol.endswith(".NS"):
                continue
            results.append({
                "symbol": symbol.replace(".NS", ""),
                "name": q.get("longname") or q.get("shortname") or "Unknown",
                "exchange": q.get("exchange", "NSE"),
                "type": q.get("quoteType", "EQUITY"),
            })
        return results

    # ───────────────────────────────────────────────
    # PRICE QUOTE — YAHOO PRIMARY (NSE is dead)
    # ───────────────────────────────────────────────
    async def _fetch_yahoo_quote(self, symbol: str) -> dict[str, Any]:
        client = await self._get_client()
        url = YAHOO_CHART_URL.format(symbol=symbol)
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            raise RuntimeError("Yahoo response missing chart result")
        
        chart = result[0]
        meta = chart.get("meta") or {}
        current_price = meta.get("regularMarketPrice")
        previous_close = meta.get("chartPreviousClose")
        
        # Fallback to last close in data array
        if current_price is None:
            quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
            closes = quote.get("close") or []
            current_price = next((v for v in reversed(closes) if v is not None), None)
        
        day_change = None
        day_change_percent = None
        if current_price and previous_close:
            day_change = current_price - previous_close
            day_change_percent = (day_change / previous_close) * 100
        
        return {
            "ticker": symbol,
            "company_name": meta.get("longName") or meta.get("shortName") or symbol,
            "current_price": current_price,
            "previous_close": previous_close,
            "day_change": round(day_change, 2) if day_change else None,
            "day_change_percent": round(day_change_percent, 2) if day_change_percent else None,
            "currency": meta.get("currency", "INR"),
            "fifty_two_week_range": meta.get("fiftyTwoWeekRange"),
            "source": "YAHOO",
        }

    async def get_quote(self, symbol: str) -> StockResult:
        """Get stock price — Yahoo primary, stale cache fallback."""
        ticker = symbol.upper().strip()
        cache_key = self._cache_key("QUOTE", ticker)
        cached = cache_service.get(cache_key)
        
        # Return fresh cache
        if cached and self._is_fresh(cached):
            return StockResult(
                data=self._decorate(self._public_payload(cached), cached=True, fresh=True),
                stale=False
            )
        
        stale = self._public_payload(cached) if cached else None
        
        try:
            value = await self._fetch_yahoo_quote(ticker)
            cache_service.set(cache_key, value, STOCK_QUOTE_CACHE_TTL_SECONDS, source="YAHOO")
            return StockResult(
                data=self._decorate(value, cached=False, fresh=True, source="YAHOO"),
                stale=False
            )
        except Exception as e:
            # Serve stale cache if Yahoo fails
            if stale:
                return StockResult(
                    data=self._decorate(
                        stale,
                        cached=True,
                        fresh=False,
                        source=stale.get("source", "YAHOO"),
                        stale_warning="Yahoo unavailable; serving stale quote",
                    ),
                    stale=True,
                    error=str(e),
                )
            return StockResult(
                data={"ticker": ticker, "error": "QUOTE_UNAVAILABLE"},
                error=str(e),
            )

    # ───────────────────────────────────────────────
    # FUNDAMENTALS — SCREENER PRIMARY (works!)
    # ───────────────────────────────────────────────
    def _company_slug(self, symbol: str) -> str:
        # Common symbol → slug mappings
        hardcoded = {
            "RELIANCE": "reliance-industries",
            "HDFCBANK": "hdfc-bank",
            "INFY": "infosys",
            "TCS": "tata-consultancy-services",
            "SBIN": "state-bank-of-india",
            "ITC": "itc",
            "ICICIBANK": "icici-bank",
            "KOTAKBANK": "kotak-mahindra-bank",
            "LT": "larsen-toubro",
            "AXISBANK": "axis-bank",
            "BAJFINANCE": "bajaj-finance",
            "BHARTIARTL": "bharti-airtel",
            "ASIANPAINT": "asian-paints",
            "MARUTI": "maruti-suzuki",
            "HCLTECH": "hcl-technologies",
            "WIPRO": "wipro",
        }
        if symbol.upper() in hardcoded:
            return hardcoded[symbol.upper()]
        # Fallback: generate slug from symbol
        return symbol.lower()

    async def _fetch_screener_fundamentals(self, symbol: str) -> dict[str, Any]:
        client = await self._get_client()
        slug = self._company_slug(symbol)
        url = SCREENER_URL.format(slug=slug)
        response = await client.get(url)
        response.raise_for_status()
        text = _strip_tags(response.text)
        
        return {
            "ticker": symbol,
            "pe": self._extract_metric(text, r"P/E\s*[:≈]?\s*([0-9.]+)"),
            "pb": self._extract_metric(text, r"P/B\s*[:≈]?\s*([0-9.]+)"),
            "roe": self._extract_metric(text, r"ROE\s*[:≈]?\s*([0-9.]+)%?"),
            "roce": self._extract_metric(text, r"ROCE\s*[:≈]?\s*([0-9.]+)%?"),
            "debt_to_equity": self._extract_metric(text, r"Debt to equity\s*[:≈]?\s*([0-9.]+)"),
            "dividend_yield": self._extract_metric(text, r"Dividend Yield\s*[:≈]?\s*([0-9.]+)%?"),
            "eps": self._extract_metric(text, r"EPS\s*[:≈]?\s*([0-9.]+)"),
            "market_cap": self._extract_metric(text, r"Market Cap\s*[:≈]?\s*[₹$]?\s*([0-9,.]+)\s*[TBC]r"),
            "source": "SCREENER",
        }

    async def get_fundamentals(self, symbol: str) -> StockResult:
        """Get stock fundamentals — Screener primary, stale cache fallback."""
        ticker = symbol.upper().strip()
        cache_key = self._cache_key("FUND", ticker)
        cached = cache_service.get(cache_key)
        
        if cached and self._is_fresh(cached):
            return StockResult(
                data=self._decorate(self._public_payload(cached), cached=True, fresh=True),
                stale=False
            )
        
        stale = self._public_payload(cached) if cached else None
        
        try:
            value = await self._fetch_screener_fundamentals(ticker)
            cache_service.set(cache_key, value, STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS, source="SCREENER")
            return StockResult(
                data=self._decorate(value, cached=False, fresh=True, source="SCREENER"),
                stale=False
            )
        except Exception as e:
            if stale:
                return StockResult(
                    data=self._decorate(
                        stale,
                        cached=True,
                        fresh=False,
                        source=stale.get("source", "SCREENER"),
                        stale_warning="Screener unavailable; serving stale fundamentals",
                    ),
                    stale=True,
                    error=str(e),
                )
            return StockResult(
                data={"ticker": ticker, "error": "FUNDAMENTALS_UNAVAILABLE"},
                error=str(e),
            )

    # ───────────────────────────────────────────────
    # COMBINED: Get everything for a stock
    # ───────────────────────────────────────────────
    async def get_stock_info(self, symbol: str) -> dict[str, Any]:
        """Get complete stock info: price + fundamentals."""
        quote_task = self.get_quote(symbol)
        fund_task = self.get_fundamentals(symbol)
        
        quote_res, fund_res = await asyncio.gather(quote_task, fund_task)
        
        return {
            "ticker": symbol,
            "price": quote_res.data,
            "fundamentals": fund_res.data,
            "errors": [
                e for e in [quote_res.error, fund_res.error] if e
            ],
        }

    @staticmethod
    def _extract_metric(text: str, pattern: str) -> float | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        return float(match.group(1)) if match else None


# ───────────────────────────────────────────────
# MODULE-LEVEL FUNCTIONS (for LangGraph tools)
# ───────────────────────────────────────────────

stock_tools = StockTools()


async def search_stocks(query: str) -> list[dict[str, Any]]:
    """Search stocks by name. Returns top matches."""
    return await stock_tools.search_by_name(query)


async def get_quote(symbol: str) -> StockResult:
    return await stock_tools.get_quote(symbol)


async def get_fundamentals(symbol: str) -> StockResult:
    return await stock_tools.get_fundamentals(symbol)


async def get_stock_info(symbol: str) -> dict[str, Any]:
    """Get complete stock info (price + fundamentals)."""
    return await stock_tools.get_stock_info(symbol)


async def get_stock_news(symbol: str, company_name: str | None = None) -> StockResult:
    # TODO: Implement with news API
    return StockResult(data={"ticker": symbol.upper(), "news": [], "error": "NEWS_UNAVAILABLE"}, stale=False)


def get_stock_tools() -> StockTools:
    return stock_tools