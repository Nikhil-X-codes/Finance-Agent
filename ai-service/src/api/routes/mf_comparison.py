"""FastAPI routes for Mutual Fund category comparison."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Query

from ...config.settings import settings
from ...services.cache_service import cache_service

logger = logging.getLogger(__name__)

router = APIRouter()

FINAPI_BASE = "https://finapi.upvaly.com"
CACHE_TTL = 3600  # 1 hour cache for live fund details and lists

CATEGORIES = [
    "Contra", "Dividend Yield", "ELSS", "Flexi Cap", "Focused",
    "Large & Mid Cap", "Large Cap", "Mid Cap", "Multi Cap",
    "Sectoral/Thematic", "Small Cap", "Value"
]


@router.get("/mf/categories")
async def get_categories() -> dict[str, list[str]]:
    """Return available MF categories for navigation tabs."""
    return {"categories": CATEGORIES}


async def _fetch_fund_detail(client: httpx.AsyncClient, scheme_code: str) -> dict[str, Any]:
    """Fetch details for a specific scheme code with caching."""
    cache_key = f"FINAPI_UPVALY_SCHEME:{scheme_code}"
    
    async def fetch():
        url = f"{FINAPI_BASE}/api/mf/scheme-code/{scheme_code}"
        params = {
            "fields": "schemeName,fundHouse,cagr,riskMetrics,fundamentals,expenseRatio,rollingReturns"
        }
        res = await client.get(url, params=params, timeout=10.0)
        res.raise_for_status()
        return res.json().get("data", {})

    try:
        # Use cache_service to load/store detailed data
        cached_result = await cache_service.get_or_fetch(
            cache_key=cache_key,
            ttl_seconds=CACHE_TTL,
            fetcher=fetch,
            source="FINAPI_UPVALY"
        )
        return cached_result.value
    except Exception as e:
        logger.warning(f"Failed to fetch detail for {scheme_code}: {e}")
        return {}


@router.get("/mf/comparison/{category}")
async def get_mf_comparison(
    category: str,
    refresh: bool = Query(default=False, description="Bypass cache and force refresh")
) -> dict[str, Any]:
    """Dynamic MF comparison by category.
    
    Fetches matching funds from FinAPI and returns enriched comparison data.
    """
    if category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Invalid category. Available: {CATEGORIES}")

    cache_key = f"FINAPI_UPVALY_CATEGORY_LIST:{category}"

    async def fetch_category_funds():
        async with httpx.AsyncClient(follow_redirects=True) as client:
            url = f"{FINAPI_BASE}/api/mf/search"
            # Fuzzy search using category name
            params = {
                "schemeName": category,
                "fields": "schemeCode,schemeName,fundHouse,schemeCategory"
            }
            res = await client.get(url, params=params, timeout=15.0)
            res.raise_for_status()
            return res.json().get("data", [])

    try:
        if refresh:
            # If force-refresh is requested, fetch directly and update cache
            funds = await fetch_category_funds()
            cache_service.set(cache_key, funds, CACHE_TTL, source="FINAPI_UPVALY")
        else:
            cached_list = await cache_service.get_or_fetch(
                cache_key=cache_key,
                ttl_seconds=CACHE_TTL,
                fetcher=fetch_category_funds,
                source="FINAPI_UPVALY"
            )
            funds = cached_list.value
    except Exception as e:
        logger.error(f"Error fetching fund search results: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"FinAPI comparison service unavailable: {str(e)}"
        )

    # Filter to only keep schemes matching the category name (to avoid broad fuzzy search noise)
    matched_funds = []
    category_lower = category.lower()
    for fund in funds:
        scheme_cat = str(fund.get("schemeCategory") or "").lower()
        # If it doesn't match the category or name, we check if it is part of it.
        # Sectoral/Thematic category names might be like "Equity - Sectoral / Thematic" or similar.
        if (category_lower in scheme_cat) or (category_lower == "sectoral/thematic" and "sector" in scheme_cat or "thematic" in scheme_cat):
            matched_funds.append(fund)
            
    # Fallback: if search by schemeCategory is too strict or empty, fall back to first 10 funds in search response
    if not matched_funds:
        matched_funds = funds[:15]

    # Limit total parallel requests to prevent overloading the FinAPI
    matched_funds = matched_funds[:12]

    # Step 2: Fetch detailed data in parallel
    enriched_funds = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = []
        for fund in matched_funds:
            # If refresh is requested, we also invalidate the individual fund cache
            scheme_code = fund.get("schemeCode")
            if not scheme_code:
                continue
            
            if refresh:
                # We can't easily tell get_or_fetch to bypass, but we can delete or fetch directly.
                # Let's fetch directly to update.
                async def fetch_direct(code=scheme_code):
                    url = f"{FINAPI_BASE}/api/mf/scheme-code/{code}"
                    params = {
                        "fields": "schemeName,fundHouse,cagr,riskMetrics,fundamentals,expenseRatio,rollingReturns"
                    }
                    res = await client.get(url, params=params, timeout=10.0)
                    res.raise_for_status()
                    data = res.json().get("data", {})
                    cache_service.set(f"FINAPI_UPVALY_SCHEME:{code}", data, CACHE_TTL, source="FINAPI_UPVALY")
                    return data
                tasks.append(fetch_direct())
            else:
                tasks.append(_fetch_fund_detail(client, str(scheme_code)))
        
        details = await asyncio.gather(*tasks, return_exceptions=True)

        for fund, detail in zip(matched_funds, details):
            if isinstance(detail, Exception) or not detail:
                continue

            # Extract rolling returns array
            rolling_list = detail.get("rollingReturns", []) or []
            rolling = {
                str(r.get("timeframe") or "").upper(): r
                for r in rolling_list if isinstance(r, dict)
            }

            risk = detail.get("riskMetrics", {}) or {}

            # Extracted risk metric resolver
            def get_latest_risk(metric_name: str) -> float | None:
                m_data = risk.get(metric_name) or {}
                timeframes = m_data.get("timeframes") or []
                if timeframes and isinstance(timeframes, list):
                    val = timeframes[0].get("value")
                    try:
                        return float(val) if val is not None else None
                    except (ValueError, TypeError):
                        return None
                return None

            # Get CAGR fields safely
            cagr = detail.get("cagr", {}) or {}

            enriched_funds.append({
                "amc": detail.get("fundHouse") or fund.get("fundHouse") or "Unknown",
                "schemeName": detail.get("schemeName") or fund.get("schemeName") or "Unknown",
                "schemeCode": fund.get("schemeCode"),
                "rollingReturns": {
                    "1Y": rolling.get("1Y", {}).get("averageReturn"),
                    "3Y": rolling.get("3Y", {}).get("averageReturn"),
                    "5Y": rolling.get("5Y", {}).get("averageReturn")
                },
                "cagr": {
                    "1Y": cagr.get("1y"),
                    "3Y": cagr.get("3y"),
                    "5Y": cagr.get("5y")
                },
                "risk": {
                    "volatility": get_latest_risk("riskStandardDeviation"),
                    "sharpe": get_latest_risk("sharpRatio"),
                    "sortino": get_latest_risk("sortinoRatio")
                },
                "others": {
                    "pe": detail.get("fundamentals", {}).get("pe") if isinstance(detail.get("fundamentals"), dict) else None,
                    "ter": detail.get("expenseRatio")
                }
            })

    return {
        "category": category,
        "dataAsOf": datetime.now().strftime("%Y-%m-%d"),
        "fundCount": len(enriched_funds),
        "funds": enriched_funds
    }
