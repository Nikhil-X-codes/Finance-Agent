"""Read-only NSE cash-market and Bhavcopy adapters for informational use."""

import asyncio
from datetime import date, datetime, timedelta
import json
import math
import re
from zoneinfo import ZoneInfo

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from src.config.settings import settings
from src.services.cache_service import cache_service

LIVE = "https://mcp.nseindia.in/cmmkt/mcp"
BHAVCOPY = "https://mcp.nseindia.in/bhavcopy/cm/mcp"
IST = ZoneInfo("Asia/Kolkata")


class NSEUnavailable(RuntimeError):
    pass


class NSEUnsupported(NSEUnavailable):
    pass


def _symbol(value: str) -> str:
    ticker = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9&.\-]{0,19}", ticker):
        raise NSEUnsupported("Unsupported NSE symbol.")
    return ticker


def _number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


async def _tool(url: str, name: str, arguments: dict) -> dict:
    async with asyncio.timeout(settings.nse_mcp_timeout_seconds):
        async with streamable_http_client(url, terminate_on_close=False) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)

    payload = result.structuredContent
    if payload is None and result.content:
        try:
            payload = json.loads(getattr(result.content[0], "text", "{}"))
        except (TypeError, ValueError) as exc:
            if result.isError and "not found" in str(getattr(result.content[0], "text", "")).lower():
                raise NSEUnsupported("No data for this NSE symbol.") from exc
            raise NSEUnavailable("Unexpected NSE response.") from exc
    if not isinstance(payload, dict):
        raise NSEUnavailable("Unexpected NSE response.")
    error = payload.get("error")
    if error or result.isError:
        if "not found" in str(error).lower():
            raise NSEUnsupported("No data for this NSE symbol.")
        raise NSEUnavailable("NSE data is unavailable.")
    return payload


def _is_recent(timestamp: datetime, now: datetime) -> bool:
    return timedelta() <= now - timestamp <= timedelta(seconds=settings.nse_quote_max_age_seconds)


async def get_nse_quote(symbol: str) -> dict:
    ticker = _symbol(symbol)

    async def fetch():
        payload = await _tool(LIVE, "cm_get_stock_quote", {"symbol": ticker})
        stock = payload.get("stock")
        if not isinstance(stock, dict) or stock.get("symbol") != ticker:
            raise NSEUnavailable("NSE quote missing its symbol.")
        price = _number(stock.get("lastTradedPrice"))
        if price is None or price <= 0 or not stock.get("latestTimestamp"):
            raise NSEUnavailable("NSE quote has no price or market timestamp.")
        timestamp = datetime.fromisoformat(stock["latestTimestamp"])
        timestamp = (timestamp.replace(tzinfo=IST) if timestamp.tzinfo is None else timestamp.astimezone(IST)).isoformat()
        high = _number(stock.get("fiftyTwoWeekHigh"))
        low = _number(stock.get("fiftyTwoWeekLow"))
        return {
            "ticker": ticker, "company_name": stock.get("companyName") or ticker,
            "current_price": price, "previous_close": _number(stock.get("preClosePrice")),
            "day_change": _number(stock.get("change")), "day_change_percent": _number(stock.get("perChange")),
            "fifty_two_week_range": f"{low:g} – {high:g}" if low is not None and high is not None else None,
            "timestamp": timestamp, "currency": "INR", "source": "NSE CM Market Live",
        }

    result = await cache_service.get_or_fetch(f"NSE:QUOTE:{ticker}", 60, fetch, source="NSE CM Market Live")
    quote = dict(result.value)
    quote.pop("_stale", None)
    market_time = datetime.fromisoformat(quote["timestamp"])
    quote["fresh"] = not result.stale and _is_recent(market_time, datetime.now(IST))
    quote["status"] = "stale_cache" if result.stale else "delayed" if quote["fresh"] else "last_published"
    return quote


async def _quote(symbol: str) -> dict:
    try:
        return await get_nse_quote(symbol)
    except NSEUnsupported:
        return {"status": "unsupported", "error": "UNSUPPORTED_SYMBOL", "source": "NSE CM Market Live"}
    except Exception:
        return {"status": "unavailable", "error": "QUOTE_UNAVAILABLE", "source": "NSE CM Market Live"}


async def _search(query: str) -> list[dict]:
    """Resolve candidates through Bhavcopy. Quote prices come from the live adapter."""
    payload = await _tool(BHAVCOPY, "search_symbols", {"query": query.strip().upper()})
    if not isinstance(payload.get("results"), list):
        raise NSEUnavailable("Unexpected Bhavcopy symbol search response.")
    matches = {}
    for item in payload["results"]:
        try:
            symbol = _symbol(item["symbol"])
        except (KeyError, TypeError, AttributeError, NSEUnsupported):
            continue
        matches.setdefault(symbol, {"symbol": symbol, "name": item.get("name") or item.get("companyName") or symbol})
        if len(matches) == 5:
            break
    return list(matches.values())


async def _movers(limit: int) -> dict[str, list[str]]:
    async def fetch():
        payload = await _tool(LIVE, "nse_get_market_movers", {"indexName": "", "limit": limit})
        groups = {}
        for direction in ("gainers", "losers"):
            rows = payload.get(direction)
            if not isinstance(rows, list):
                raise NSEUnavailable("Unexpected market movers response.")
            symbols = {}
            for row in rows:
                value = row.get("symbol") if isinstance(row, dict) else None
                if not isinstance(value, str):
                    continue
                try:
                    symbols[_symbol(value)] = None
                except NSEUnsupported:
                    continue
            groups[direction] = list(symbols)[:limit]
        return groups

    result = await cache_service.get_or_fetch(f"NSE:MOVERS:{limit}", 60, fetch, source="NSE CM Market Live")
    if result.stale:
        raise NSEUnavailable("The market movers ranking is temporarily unavailable.")
    return {direction: result.value[direction] for direction in ("gainers", "losers")}


async def _history_rows(symbol: str, end: str) -> list[dict]:
    async def fetch():
        payload = await _tool(BHAVCOPY, "get_stock_history", {"symbol": symbol, "months": 1, "endDate": end})
        if payload.get("symbol") != symbol or not isinstance(payload.get("data"), list):
            raise NSEUnavailable("Bhavcopy history missing expected fields.")
        rows = {}
        for row in payload["data"]:
            if row.get("symbol") not in (None, symbol):
                continue
            try:
                day = date.fromisoformat(row["date"]).isoformat()
            except (KeyError, TypeError, ValueError):
                continue
            fields = {key: _number(row.get(key)) for key in ("open", "high", "low", "close", "volume")}
            if fields["close"] is not None and fields["close"] > 0:
                rows[day] = {"date": day, **fields}
        if not rows:
            raise NSEUnsupported("No sessions for this NSE symbol or date.")
        return [rows[key] for key in sorted(rows)]

    result = await cache_service.get_or_fetch(f"NSE:OHLCV:{symbol}:{end}", 900, fetch, source="NSE Bhavcopy")
    return result.value


def adjusted_price_return(rows: list[dict], actions: list[dict]) -> float | None:
    """Verify split and bonus factors before comparing first and last closes."""
    if len(rows) < 2:
        return None
    start, end = rows[0]["date"], rows[-1]["date"]
    factor = 1.0
    for action in actions:
        kind = action.get("actionType", "").upper()
        purpose = str(action.get("purpose") or "").lower()
        if kind not in {"SPLIT", "BONUS"} and not any(word in purpose for word in ("split", "sub-division", "bonus", "consolidation")):
            continue
        try:
            when = date.fromisoformat(action["exDate"]).isoformat()
        except (KeyError, TypeError, ValueError):
            return None
        if start < when <= end:
            value = _number(action.get("adjustmentFactor"))
            if value is None or value <= 0:
                return None
            factor *= value
    return round((rows[-1]["close"] / (rows[0]["close"] * factor) - 1) * 100, 2)


async def _history(symbol: str) -> dict:
    try:
        ticker = _symbol(symbol)
        rows = await _history_rows(ticker, "today")
    except NSEUnsupported:
        return {"status": "unsupported"}
    except Exception:
        return {"status": "unavailable"}
    adjusted = None
    try:
        start, end = rows[0]["date"], rows[-1]["date"]

        async def fetch_actions():
            data = await _tool(BHAVCOPY, "get_corporate_actions", {"symbol": ticker, "fromDate": start, "toDate": end})
            items = data.get("actions")
            if data.get("symbol") != ticker or not isinstance(items, list) or data.get("count") != len(items):
                raise NSEUnavailable("Incomplete corporate action coverage.")
            return items

        actions = await cache_service.get_or_fetch(f"NSE:ACTIONS:{ticker}:{start}:{end}", 86400, fetch_actions, source="NSE Bhavcopy")
        if not actions.stale:
            adjusted = adjusted_price_return(rows, actions.value)
    except Exception:
        pass
    return {
        "status": "available", "source": "NSE Bhavcopy", "asOf": rows[-1]["date"], "points": rows,
        "adjustedPriceReturnPercent": adjusted, "adjustment": "split_bonus" if adjusted is not None else "unverified",
    }


async def _historical_close(symbol: str, when: date) -> dict:
    if when > datetime.now(IST).date():
        return {}
    try:
        ticker = _symbol(symbol)
        rows = await _history_rows(ticker, when.isoformat())
    except Exception:
        return {}
    if rows[-1]["date"] != when.isoformat():
        return {}
    return {
        "current_price": rows[-1]["close"], "currency": "INR", "timestamp": rows[-1]["date"],
        "source": "NSE Bhavcopy", "fresh": False,
    }


async def _index_snapshot() -> dict:
    source = "NSE CM Market Live"

    async def fetch():
        payload = await _tool(LIVE, "cm_get_index_quote", {"indexName": "NIFTY 50"})
        index = payload.get("index") or {}
        value = _number(index.get("last"))
        if payload.get("warning") or index.get("indexName") != "NIFTY 50" or value is None or value <= 0:
            raise NSEUnavailable("NIFTY 50 snapshot is unavailable.")
        timestamp = datetime.strptime(payload["nseTimestamp"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
        return {
            "name": "NIFTY 50", "value": value, "dayChangePercent": _number(index.get("percChange")),
            "timestamp": timestamp.isoformat(), "source": source,
        }

    try:
        result = await cache_service.get_or_fetch("NSE:INDEX:NIFTY50", 300, fetch, source=source)
        return {**result.value, "status": "cached" if result.stale else "last_published"}
    except Exception:
        return {}


class NseMcpProvider:
    quote = staticmethod(_quote)
    search = staticmethod(_search)
    history = staticmethod(_history)
    historical_close = staticmethod(_historical_close)
    movers = staticmethod(_movers)
    index_snapshot = staticmethod(_index_snapshot)
