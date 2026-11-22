"""Compare category-matched funds using MFapi.in NAV data."""

import asyncio
from datetime import datetime
import logging
import math
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from src.core.tools.mf_tools import MFAPI_SOURCE, fetch_mfapi_scheme, get_mfapi_catalog
from src.services.cache_service import cache_service

logger = logging.getLogger(__name__)
router = APIRouter()
CACHE_TTL = 3600
FUND_LIMIT = 12
SCHEME_NAME_TERMS = {
    "Contra": ("Contra",),
    "Dividend Yield": ("Dividend Yield",),
    "ELSS": ("ELSS", "Tax Saver", "Tax Saving"),
    "Flexi Cap": ("Flexi Cap", "Flexicap"),
    "Focused": ("Focused",),
    "Large & Mid Cap": ("Large & Mid Cap", "Large and Mid Cap", "Large Mid Cap"),
    "Large Cap": ("Large Cap", "Largecap", "Bluechip"),
    "Mid Cap": ("Mid Cap", "Midcap"),
    "Multi Cap": ("Multi Cap", "Multicap"),
    "Sectoral/Thematic": ("Sectoral", "Thematic", "Infrastructure", "Technology", "Pharma"),
    "Small Cap": ("Small Cap", "Smallcap"),
    "Value": ("Value",),
}
CATEGORIES = list(SCHEME_NAME_TERMS)


@router.get("/mf/categories")
async def get_categories() -> dict[str, list[str]]:
    return {"categories": CATEGORIES}


def _category_key(label: str) -> str:
    label = re.sub(r"^Equity Scheme\s*-\s*", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\band\b|\bfund\b", "", label, flags=re.IGNORECASE)
    return re.sub(r"[^a-z]", "", label.lower())


def _fund_row(payload: dict, category: str) -> dict | None:
    meta = payload["meta"]
    if _category_key(meta["scheme_category"]) != _category_key(category):
        return None

    latest = next(iter(payload["data"]), None)
    if latest is None:
        return None
    nav = float(latest["nav"])
    if not math.isfinite(nav) or nav <= 0:
        return None
    nav_date = datetime.strptime(latest["date"], "%d-%m-%Y").date().isoformat()
    return {
        "amc": meta["fund_house"],
        "schemeName": meta["scheme_name"],
        "schemeCode": meta["scheme_code"],
        "plan": None,
        "option": None,
        "nav": nav,
        "navDate": nav_date,
        "rollingReturns": dict.fromkeys(("1Y", "3Y", "5Y")),
        "cagr": dict.fromkeys(("1Y", "3Y", "5Y")),
        "risk": dict.fromkeys(("volatility", "sharpe", "sortino")),
        "others": dict.fromkeys(("pe", "ter")),
    }


def _scheme_codes(catalog: list[dict], category: str) -> list[str]:
    terms = [_category_key(term) for term in SCHEME_NAME_TERMS[category]]
    candidates = {}
    # Registered direct growth plans generally have an ISIN and fewer discontinued entries.
    for scheme in catalog:
        if not isinstance(scheme, dict):
            continue
        code = str(scheme.get("schemeCode", ""))
        raw_name = str(scheme.get("schemeName", ""))
        name = _category_key(raw_name)
        if re.search(r"\b(?:index fund|etf)\b", raw_name, flags=re.IGNORECASE):
            continue
        if category == "Mid Cap" and "largemidcap" in name:
            continue
        if code.isascii() and code.isdecimal() and any(term in name for term in terms):
            direct_growth = "direct" in name and "growth" in name and "idcw" not in name
            has_isin = bool(scheme.get("isinGrowth") or scheme.get("isinDivReinvestment"))
            candidates[code] = (has_isin, direct_growth, int(code))
    return sorted(candidates, key=candidates.__getitem__, reverse=True)


async def _fetch_comparison(client: httpx.AsyncClient, category: str) -> list[dict]:
    async def fetch_row(code: str) -> dict | None:
        return _fund_row(await fetch_mfapi_scheme(client, code), category)

    catalog = await get_mfapi_catalog(client)
    candidates = _scheme_codes(catalog, category)[:4 * FUND_LIMIT]
    rows = []
    any_details = False
    for start in range(0, len(candidates), FUND_LIMIT):
        results = await asyncio.gather(
            *(fetch_row(code) for code in candidates[start:start + FUND_LIMIT]),
            return_exceptions=True,
        )
        any_details |= any(not isinstance(result, Exception) for result in results)
        rows.extend(row for row in results if isinstance(row, dict))
        if len(rows) >= FUND_LIMIT:
            break
    if candidates and not any_details:
        raise ValueError("MFapi.in fund details are unavailable.")
    return rows[:FUND_LIMIT]


@router.get("/mf/comparison/{category:path}")
async def get_mf_comparison(category: str, refresh: bool = Query(default=False)) -> dict[str, Any]:
    if category not in SCHEME_NAME_TERMS:
        raise HTTPException(422, "Invalid fund category.")

    key = f"MFAPI_COMPARISON:{category}"

    async def fetch():
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            return await _fetch_comparison(client, category)

    try:
        if refresh:
            rows = await fetch()
            await cache_service.set(key, rows, CACHE_TTL, source=MFAPI_SOURCE)
        else:
            rows = (await cache_service.get_or_fetch(key, CACHE_TTL, fetch, source=MFAPI_SOURCE)).value
    except Exception as exc:
        logger.warning("Fund comparison failed for %s: %s", category, type(exc).__name__)
        raise HTTPException(502, "Fund data is temporarily unavailable.") from exc

    return {
        "category": category,
        "source": MFAPI_SOURCE,
        "dataAsOf": None,
        "fundCount": len(rows),
        "funds": rows,
    }
