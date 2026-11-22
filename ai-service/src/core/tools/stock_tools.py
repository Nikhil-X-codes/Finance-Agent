"""Company fundamentals from Screener."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

import httpx

from ...config.settings import settings
from ...services.cache_service import cache_service

SCREENER_URL = "https://www.screener.in/company/{symbol}/consolidated/"


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
    # FUNDAMENTALS — SCREENER PRIMARY (works!)
    # ───────────────────────────────────────────────
    async def _fetch_screener_fundamentals(self, symbol: str) -> dict[str, Any]:
        client = await self._get_client()
        url = SCREENER_URL.format(symbol=quote(symbol, safe=""))
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
        cached = await cache_service.get(cache_key)
        
        if cached and self._is_fresh(cached):
            return StockResult(
                data=self._decorate(self._public_payload(cached), cached=True, fresh=True),
                stale=False
            )
        
        stale = self._public_payload(cached) if cached else None
        
        try:
            value = await self._fetch_screener_fundamentals(ticker)
            await cache_service.set(cache_key, value, settings.stock_fundamentals_cache_ttl_seconds, source="SCREENER")
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

    @staticmethod
    def _extract_metric(text: str, pattern: str) -> float | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        try:
            return float(match.group(1).replace(",", "")) if match else None
        except ValueError:
            return None


# ───────────────────────────────────────────────
# MODULE-LEVEL FUNCTIONS (for LangGraph tools)
# ───────────────────────────────────────────────

stock_tools = StockTools()


async def get_fundamentals(symbol: str) -> StockResult:
    return await stock_tools.get_fundamentals(symbol)
