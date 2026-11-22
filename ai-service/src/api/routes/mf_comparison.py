"""Compare category-matched funds using FinAPI data."""

import asyncio
import logging
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from src.config.settings import settings
from src.services.cache_service import cache_service

logger = logging.getLogger(__name__)
router = APIRouter()
FINAPI_BASE = "https://finapi.upvaly.com/api/mf"
SOURCE = "FinAPI"
CACHE_TTL = 3600
CATEGORIES = [
    "Contra", "Dividend Yield", "ELSS", "Flexi Cap", "Focused",
    "Large & Mid Cap", "Large Cap", "Mid Cap", "Multi Cap",
    "Sectoral/Thematic", "Small Cap", "Value",
]
BASIC_FIELDS = "schemeCode,schemeName,schemeCategoryLabel,fundHouse,planName,optionName,latestNav,latestNavDate"
DETAIL_FIELDS = BASIC_FIELDS + ",cagr,riskMetrics,fundamentals,expenseRatio,rollingReturns"


@router.get("/mf/categories")
async def get_categories() -> dict[str, list[str]]:
    return {"categories": CATEGORIES}


def _matches_category(fund: dict, category: str) -> bool:
    label = fund.get("schemeCategoryLabel") or fund.get("schemeCategory") or ""
    words = " ".join(re.findall(r"[a-z0-9]+", str(label).lower()))
    if category == "Sectoral/Thematic":
        return "sectoral" in words or "thematic" in words
    category_words = " ".join(re.findall(r"[a-z0-9]+", category.lower()))
    return f" {category_words} " in f" {words} "


async def _read(client: httpx.AsyncClient, path: str, params: dict) -> Any:
    response = await client.get(f"{FINAPI_BASE}/{path}", params=params)
    response.raise_for_status()
    return response.json()["data"]


async def _fetch_fund_detail(client: httpx.AsyncClient, scheme_code: str, refresh: bool) -> dict:
    key = f"FINAPI_UPVALY_SCHEME:{scheme_code}"

    async def fetch():
        detail = await _read(client, f"scheme-code/{scheme_code}", {"fields": DETAIL_FIELDS})
        if not isinstance(detail, dict):
            raise ValueError("FinAPI returned invalid fund details")
        return detail

    if refresh:
        detail = await fetch()
        await cache_service.set(key, detail, CACHE_TTL, source=SOURCE)
        return detail
    return (await cache_service.get_or_fetch(key, CACHE_TTL, fetch, source=SOURCE)).value


def _fund_row(fund: dict, detail: dict) -> dict:
    fund = {**fund, **{field: value for field, value in detail.items() if value is not None}}
    rolling = {
        str(item.get("timeframe") or "").upper(): item.get("averageReturn")
        for item in fund.get("rollingReturns") or [] if isinstance(item, dict)
    }
    cagr = fund["cagr"] if isinstance(fund.get("cagr"), dict) else {}
    risk = fund["riskMetrics"] if isinstance(fund.get("riskMetrics"), dict) else {}
    fundamentals = fund["fundamentals"] if isinstance(fund.get("fundamentals"), dict) else {}

    def risk_value(key):
        metric = risk.get(key)
        windows = metric.get("timeframes") if isinstance(metric, dict) else None
        return windows[0].get("value") if isinstance(windows, list) and windows and isinstance(windows[0], dict) else None

    return {
        "amc": fund.get("fundHouse"),
        "schemeName": fund["schemeName"],
        "schemeCode": fund["schemeCode"],
        "plan": fund.get("planName"),
        "option": fund.get("optionName"),
        "nav": fund.get("latestNav"),
        "navDate": fund.get("latestNavDate"),
        "rollingReturns": {period: rolling.get(period) for period in ("1Y", "3Y", "5Y")},
        "cagr": {period: cagr.get(period) if period in cagr else cagr.get(period.lower()) for period in ("1Y", "3Y", "5Y")},
        "risk": {
            "volatility": risk_value("riskStandardDeviation"),
            "sharpe": risk_value("sharpRatio"),
            "sortino": risk_value("sortinoRatio"),
        },
        "others": {"pe": fundamentals.get("pe"), "ter": fund.get("expenseRatio")},
    }


@router.get("/mf/comparison/{category:path}")
async def get_mf_comparison(
    category: str, refresh: bool = Query(default=False),
) -> dict[str, Any]:
    if category not in CATEGORIES:
        raise HTTPException(422, "Invalid fund category.")

    headers = {"X-API-Key": settings.finapi_upvaly_api_key} if settings.finapi_upvaly_api_key else {}
    async with httpx.AsyncClient(headers=headers, timeout=12, follow_redirects=True) as client:
        async def search_by_name(term: str) -> list:
            # FinAPI searches by scheme name and supplies the authoritative category label.
            data = await _read(client, "search", {"schemeName": term, "fields": BASIC_FIELDS})
            if not isinstance(data, list):
                raise ValueError("FinAPI returned invalid fund search results")
            return data

        async def search() -> list:
            if category != "Sectoral/Thematic":
                return await search_by_name(category)
            batches = await asyncio.gather(
                *(search_by_name(term) for term in ("Infrastructure", "Technology", "Pharma")),
                return_exceptions=True,
            )
            successful = [batch for batch in batches if isinstance(batch, list)]
            if not successful:
                raise ValueError("FinAPI sectoral fund search failed.")
            # Interleave search results so one sector cannot fill the entire comparison.
            return [
                batch[index]
                for index in range(max(map(len, successful), default=0))
                for batch in successful if index < len(batch)
            ]

        key = f"FINAPI_UPVALY_CATEGORY_LIST:v2:{category}"
        try:
            if refresh:
                funds = await search()
                await cache_service.set(key, funds, CACHE_TTL, source=SOURCE)
            else:
                cached = await cache_service.get_or_fetch(key, CACHE_TTL, search, source=SOURCE)
                funds = cached.value
        except Exception as exc:
            logger.warning("Fund search failed for %s: %s", category, type(exc).__name__)
            raise HTTPException(502, "Fund data is temporarily unavailable.") from exc

        matched_by_code = {
            str(fund["schemeCode"]): fund for fund in funds
            if isinstance(fund, dict) and str(fund.get("schemeCode", "")).isdigit()
            and fund.get("schemeName") and _matches_category(fund, category)
        }
        matched = list(matched_by_code.values())[:12]
        details = await asyncio.gather(
            *(_fetch_fund_detail(client, str(fund["schemeCode"]), refresh) for fund in matched),
            return_exceptions=True,
        )
        rows = [
            _fund_row(fund, detail if isinstance(detail, dict) else {})
            for fund, detail in zip(matched, details)
        ]

    return {"category": category, "source": SOURCE, "dataAsOf": None, "fundCount": len(rows), "funds": rows}
