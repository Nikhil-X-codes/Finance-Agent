"""News tool with NewsAPI primary — reliable, no HTML scraping."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ...config.constants import STOCK_NEWS_CACHE_TTL_SECONDS
from ...services.cache_service import cache_service

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = "https://newsapi.org/v2/everything"


@dataclass(slots=True)
class NewsResult:
    data: dict[str, Any]
    stale: bool = False
    error: str | None = None


class NewsTools:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._api_key = NEWS_API_KEY

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        return self._client

    @staticmethod
    def _cache_key(symbol: str) -> str:
        return f"NEWS:{symbol.upper()}"

    @staticmethod
    def _is_fresh(payload: dict[str, Any]) -> bool:
        expires_at = int(payload.get("_cache_expires_at", 0) or 0)
        return expires_at > int(time.time())

    @staticmethod
    def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in payload.items() if k not in {"_cache_expires_at", "_stale"}}

    async def _fetch_google_rss(self, symbol: str, company_name: str | None = None) -> list[dict[str, Any]]:
        """Fetch news from Google News RSS."""
        from urllib.parse import quote_plus
        import xml.etree.ElementTree as ET
        
        client = await self._get_client()
        query_term = company_name if company_name else f"{symbol} stock"
        query = quote_plus(f"{query_term} India")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        response = await client.get(url)
        response.raise_for_status()
        
        root = ET.fromstring(response.text)
        items = root.findall(".//item")
        
        articles = []
        for item in items[:5]:
            title = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else None
            source = item.find("source").text if item.find("source") is not None else "Google News"
            description = item.find("description").text if item.find("description") is not None else None
            
            if not title:
                continue
                
            articles.append({
                "title": title,
                "url": link,
                "source": source,
                "published_at": pub_date,
                "summary": description,
            })
        return articles

    async def _fetch_newsapi(self, symbol: str, company_name: str | None = None) -> list[dict[str, Any]]:
        """Fetch news from NewsAPI."""
        if not self._api_key:
            raise RuntimeError("NEWS_API_KEY not set. Get free key from newsapi.org")
        
        client = await self._get_client()
        query_term = company_name if company_name else f"{symbol} stock"
        params = {
            "q": f"{query_term} India",
            "apiKey": self._api_key,
            "pageSize": 5,
            "sortBy": "publishedAt",
            "language": "en",
        }
        
        response = await client.get(NEWS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "ok":
            raise RuntimeError(f"NewsAPI error: {data.get('message', 'Unknown')}")
        
        articles = []
        for a in data.get("articles", []):
            articles.append({
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "source": a.get("source", {}).get("name", "NewsAPI"),
                "published_at": a.get("publishedAt"),
                "summary": a.get("description"),
            })
        
        return articles

    async def get_stock_news(self, symbol: str, company_name: str | None = None) -> NewsResult:
        ticker = symbol.upper().strip()
        cache_key = self._cache_key(ticker)
        cached = cache_service.get(cache_key)
        
        # Return fresh cache
        if cached is not None and self._is_fresh(cached):
            payload = self._public_payload(cached)
            payload["cached"] = True
            payload["fresh"] = True
            return NewsResult(data=payload, stale=False)
        
        stale_payload = self._public_payload(cached) if cached else None
        
        # Try Google News RSS first
        try:
            articles = await self._fetch_google_rss(ticker, company_name)
            if articles:
                value = {
                    "ticker": ticker,
                    "news": articles,
                    "source": "GoogleNewsRSS",
                    "cached": False,
                    "fresh": True,
                }
                cache_service.set(cache_key, value, STOCK_NEWS_CACHE_TTL_SECONDS, source="GoogleNewsRSS")
                return NewsResult(data=value, stale=False)
        except Exception as rss_error:
            pass
            
        # Fallback to NewsAPI
        try:
            articles = await self._fetch_newsapi(ticker, company_name)
            
            if not articles:
                return NewsResult(
                    data={"ticker": ticker, "news": [], "source": "NewsAPI", "cached": False, "fresh": True},
                    stale=False
                )
            
            value = {
                "ticker": ticker,
                "news": articles,
                "source": "NewsAPI",
                "cached": False,
                "fresh": True,
            }
            cache_service.set(cache_key, value, STOCK_NEWS_CACHE_TTL_SECONDS, source="NewsAPI")
            return NewsResult(data=value, stale=False)
            
        except Exception as exc:
            # Serve stale cache if available
            if stale_payload is not None:
                stale_payload["cached"] = True
                stale_payload["fresh"] = False
                stale_payload["stale_warning"] = "News sources unavailable; serving stale news"
                return NewsResult(data=stale_payload, stale=True, error=str(exc))
            
            return NewsResult(
                data={"ticker": ticker, "news": [], "source": "NewsAPI", "cached": False, "fresh": False, "error": "NEWS_UNAVAILABLE"},
                stale=False,
                error=str(exc)
            )


news_tools = NewsTools()


async def get_stock_news(symbol: str, company_name: str | None = None) -> NewsResult:
    return await news_tools.get_stock_news(symbol, company_name)


async def get_news(symbol: str | None = None, company_name: str | None = None) -> dict[str, Any]:
    result = await news_tools.get_stock_news(symbol or "")
    return {"data": result.data, "stale": result.stale, "error": result.error}


def get_news_tools() -> NewsTools:
    return news_tools








