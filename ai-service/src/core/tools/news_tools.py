"""Public stock news with dated provenance and report selection."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import re
from typing import Any
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import httpx

from src.config.settings import settings
from src.services.cache_service import cache_service

NEWS_WINDOW_DAYS = 30
NEWS_LIMIT = 6
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"
NEWS_API_URL = "https://newsapi.org/v2/everything"


@dataclass(slots=True)
class NewsResult:
    data: dict[str, Any]
    stale: bool = False
    error: str | None = None


def _published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        try:
            published = datetime.fromisoformat(value)
        except ValueError:
            published = parsedate_to_datetime(value)
        if published.tzinfo is not None:
            return published.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _recent_articles(articles: list[dict], now: datetime) -> list[dict]:
    cutoff = now - timedelta(days=NEWS_WINDOW_DAYS)
    rows = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        published = _published_at(article.get("published_at") or article.get("publishedAt"))
        if published is None or not cutoff <= published <= now:
            continue
        url = article.get("url") or ""
        try:
            url_parts = urlsplit(url)
        except (TypeError, ValueError):
            continue
        if url_parts.scheme not in {"http", "https"} or not url_parts.hostname or url_parts.username:
            continue
        title = " ".join(unescape(str(article.get("title") or "")).split())
        if title:
            rows.append({
                "title": title, "url": url, "source": str(article.get("source") or "Unknown publisher"),
                "publishedAt": published.isoformat(),
            })
    return sorted(rows, key=lambda row: row["publishedAt"], reverse=True)


def _headline(title: str, source: str) -> set[str]:
    suffix = f" - {source}"
    if title.casefold().endswith(suffix.casefold()):
        title = title[:-len(suffix)]
    return set(re.findall(r"[a-z0-9]+", title.casefold()))


def _matches_company(article: dict, company: str, ticker: str) -> bool:
    title = article["title"].rsplit(f" - {article['source']}", 1)[0].casefold()
    compact_title = "".join(re.findall(r"[a-z0-9]+", title))
    compact_name = "".join(re.findall(r"[a-z0-9]+", company.casefold()))
    title_words = set(re.findall(r"[a-z0-9&]+", title))
    return bool((len(compact_name) >= 4 and compact_name in compact_title)
                or (len(ticker) >= 3 and ticker.casefold() in title_words))


def select_report_news(batches: dict[str, list[dict]], now: datetime) -> list[dict]:
    """Prefer coverage across holdings and suppress repeated versions of the same headline."""
    selected = []
    urls = set()
    headlines = []

    def take(ticker: str, limit: int):
        for article in _recent_articles(batches.get(ticker, []), now):
            words = _headline(article["title"], article["source"])
            url = article["url"]
            if not words or url in urls or any(len(words & seen) / len(words | seen) >= 0.72 for seen in headlines):
                continue
            urls.add(url)
            headlines.append(words)
            selected.append({**article, "ticker": ticker})
            if sum(row["ticker"] == ticker for row in selected) >= limit or len(selected) >= NEWS_LIMIT:
                break

    for ticker in batches:
        if ticker != "MARKET" and len(selected) < NEWS_LIMIT - 1:
            take(ticker, 1)
    if len(selected) < NEWS_LIMIT:
        take("MARKET", 1)
    for ticker in batches:
        if ticker != "MARKET" and len(selected) < NEWS_LIMIT:
            take(ticker, 2)
    return selected


class NewsTools:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=8, follow_redirects=True)
        return self._client

    async def _google(self, query: str) -> list[dict]:
        client = await self._get_client()
        response = await client.get(GOOGLE_NEWS_URL, params={"q": f"{query} when:{NEWS_WINDOW_DAYS}d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        return [{
            "title": item.findtext("title"), "url": item.findtext("link"),
            "source": item.findtext("source"), "published_at": item.findtext("pubDate"),
        } for item in root.findall("./channel/item")[:15]]

    async def _newsapi(self, query: str, now: datetime) -> list[dict]:
        key = settings.newsapi_key
        if not key:
            raise RuntimeError("NewsAPI is not configured.")
        client = await self._get_client()
        response = await client.get(NEWS_API_URL, headers={"X-Api-Key": key}, params={
            "q": query, "from": (now - timedelta(days=NEWS_WINDOW_DAYS)).date().isoformat(),
            "pageSize": 15, "sortBy": "publishedAt", "language": "en",
        })
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "ok":
            raise RuntimeError("NewsAPI failed.")
        return [{
            "title": item.get("title"), "url": item.get("url"),
            "source": (item.get("source") or {}).get("name"), "published_at": item.get("publishedAt"),
        } for item in data.get("articles", [])]

    async def get_stock_news(self, symbol: str, company_name: str | None = None) -> NewsResult:
        now = datetime.now(timezone.utc)
        ticker = symbol.strip().upper()
        public_name = re.sub(r"[^\w .&-]", " ", company_name or "").strip()
        public_name = re.sub(r"(?:[\s.]+(?:limited|ltd|plc)\.?)+$", "", public_name, flags=re.IGNORECASE)
        query = '("Nifty 50" OR "Indian stock market")' if ticker == "MARKET" else f'"{public_name or ticker}" stock India'

        def relevant(rows):
            dated = _recent_articles(rows, now)
            return dated if ticker == "MARKET" else [row for row in dated if _matches_company(row, public_name, ticker)]

        async def fetch():
            try:
                articles = relevant(await self._google(query))
            except Exception:
                articles = None
            if articles:
                return {"news": articles, "source": "Google News RSS"}
            if settings.newsapi_key:
                return {"news": relevant(await self._newsapi(query, now)), "source": "NewsAPI"}
            if articles is None:
                raise RuntimeError("News sources unavailable.")
            return {"news": [], "source": "Google News RSS"}

        try:
            cached = await cache_service.get_or_fetch(
                f"NEWS:v2:{ticker}:{public_name.casefold()}", settings.stock_news_cache_ttl_seconds, fetch,
            )
            return NewsResult(cached.value, stale=cached.stale)
        except Exception as exc:
            return NewsResult({"news": []}, error=type(exc).__name__)


news_tools = NewsTools()


async def get_stock_news(symbol: str, company_name: str | None = None) -> NewsResult:
    return await news_tools.get_stock_news(symbol, company_name)
