"""Enricher node for parallel market data fetching and normalization."""

from __future__ import annotations

import asyncio
from typing import Any

from src.config.models import Holding
from src.core.tools.mf_tools import get_holdings, get_metadata, get_nav
from src.core.tools.news_tools import get_stock_news
from src.core.tools.stock_tools import get_fundamentals, get_quote
from ..state import PortfolioState


async def enrich_portfolio(state: PortfolioState) -> dict[str, Any]:
    """Fetch market data, fundamentals, news, and macro context in parallel."""
    normalized_holdings = state.get("normalized_holdings") or []
    include_news = state.get("include_news", True)
    errors: list[dict[str, str]] = list(state.get("errors") or [])

    if not normalized_holdings:
        return {
            "enriched_holdings": [],
            "macro_context": {},
            "current_node": "enricher"
        }

    # 1. Prepare parallel tasks
    stock_tasks: list[tuple[Holding, Any, Any, Any | None]] = []
    mf_tasks: list[tuple[Holding, Any, Any, Any]] = []
    realized_holdings: list[Holding] = []

    for h in normalized_holdings:
        if h.status == "REALIZED" or h.quantity == 0:
            realized_holdings.append(h)
            continue

        if h.asset_type == "STOCK":
            quote_t = get_quote(h.ticker)
            fund_t = get_fundamentals(h.ticker)
            news_t = get_stock_news(h.ticker, h.name) if include_news else None
            stock_tasks.append((h, quote_t, fund_t, news_t))
        elif h.asset_type == "MUTUAL_FUND":
            nav_t = get_nav(h.isin)
            meta_t = get_metadata(h.isin)
            holdings_t = get_holdings(h.isin)
            mf_tasks.append((h, nav_t, meta_t, holdings_t))

    # 2. Gather all tasks concurrently
    flat_tasks: list[Any] = []
    for _, quote_t, fund_t, news_t in stock_tasks:
        flat_tasks.extend([quote_t, fund_t])
        if news_t is not None:
            flat_tasks.append(news_t)
            
    for _, nav_t, meta_t, holdings_t in mf_tasks:
        flat_tasks.extend([nav_t, meta_t, holdings_t])

    results = await asyncio.gather(*flat_tasks, return_exceptions=True)

    # 3. Parse results back to holdings
    result_idx = 0
    enriched: list[dict[str, Any]] = []
    total_portfolio_value = 0.0

    # Process stocks
    for h, _, _, news_t in stock_tasks:
        quote_res = results[result_idx]
        fund_res = results[result_idx + 1]
        result_idx += 2

        news_res = None
        if news_t is not None:
            news_res = results[result_idx]
            result_idx += 1

        # Extract quote
        quote_data = {}
        if not isinstance(quote_res, Exception) and quote_res.data:
            quote_data = quote_res.data
        else:
            errors.append({
                "code": "STOCK_QUOTE_FAILED",
                "message": f"Failed to fetch stock quote for {h.ticker}: {quote_res}"
            })

        # Extract fundamentals
        fund_data = {}
        if not isinstance(fund_res, Exception) and fund_res.data:
            fund_data = fund_res.data
        else:
            errors.append({
                "code": "STOCK_FUNDAMENTALS_FAILED",
                "message": f"Failed to fetch stock fundamentals for {h.ticker}: {fund_res}"
            })

        # Extract news
        news_list = []
        if news_res is not None and not isinstance(news_res, Exception) and news_res.data:
            news_list = news_res.data.get("news", [])

        current_price = float(quote_data.get("current_price") or h.avg_buy_price)
        holding_value = h.quantity * current_price
        total_portfolio_value += holding_value

        enriched.append({
            "isin": h.isin,
            "ticker": h.ticker,
            "name": h.name,
            "quantity": h.quantity,
            "avg_buy_price": h.avg_buy_price,
            "asset_type": "STOCK",
            "sector": h.sector or fund_data.get("sector") or "Unknown",
            "current_price": current_price,
            "day_change": quote_data.get("day_change", 0.0),
            "p_change": quote_data.get("p_change", 0.0),
            "fundamentals": fund_data,
            "news": news_list,
            "value": holding_value,
            "fresh": quote_data.get("fresh", True) and fund_data.get("fresh", True)
        })

    # Process Mutual Funds
    for h, _, _, _ in mf_tasks:
        nav_res = results[result_idx]
        meta_res = results[result_idx + 1]
        holdings_res = results[result_idx + 2]
        result_idx += 3

        # Extract NAV
        nav_data = {}
        if not isinstance(nav_res, Exception) and nav_res.data:
            nav_data = nav_res.data
        else:
            errors.append({
                "code": "MF_NAV_FAILED",
                "message": f"Failed to fetch MF NAV for {h.isin}: {nav_res}"
            })

        # Extract Metadata
        meta_data = {}
        if not isinstance(meta_res, Exception) and meta_res.data:
            meta_data = meta_res.data
        else:
            errors.append({
                "code": "MF_METADATA_FAILED",
                "message": f"Failed to fetch MF metadata for {h.isin}: {meta_res}"
            })

        # Extract Holdings
        holdings_data = {}
        if not isinstance(holdings_res, Exception) and holdings_res.data:
            holdings_data = holdings_res.data
        else:
            errors.append({
                "code": "MF_HOLDINGS_FAILED",
                "message": f"Failed to fetch MF portfolio holdings for {h.isin}: {holdings_res}"
            })

        nav = float(nav_data.get("nav") or h.avg_buy_price)
        holding_value = h.quantity * nav
        total_portfolio_value += holding_value

        enriched.append({
            "isin": h.isin,
            "ticker": h.ticker,
            "name": h.name,
            "quantity": h.quantity,
            "avg_buy_price": h.avg_buy_price,
            "asset_type": "MUTUAL_FUND",
            "sector": h.sector or meta_data.get("category") or "Mutual Fund",
            "nav": nav,
            "expense_ratio": meta_data.get("expense_ratio") or 0.0,
            "aum": meta_data.get("aum") or 0.0,
            "category": meta_data.get("category") or "Unknown",
            "benchmark": meta_data.get("benchmark") or "Unknown",
            "holdings": holdings_data.get("holdings", []),
            "value": holding_value,
            "fresh": nav_data.get("fresh", True) and meta_data.get("fresh", True)
        })

    # Compute portfolio weights
    if total_portfolio_value > 0:
        for item in enriched:
            item["portfolio_weight"] = item["value"] / total_portfolio_value
    else:
        for item in enriched:
            item["portfolio_weight"] = 0.0

    # Append realized holdings with 0 value/weight
    for h in realized_holdings:
        realized_pnl = h.realized_pnl
        if realized_pnl is None and h.sell_price is not None:
            realized_pnl = (h.sell_price - h.avg_buy_price) * (h.quantity if h.quantity > 0 else 1.0)
            
        enriched.append({
            "isin": h.isin or "INE000000000",
            "ticker": h.ticker,
            "name": h.name,
            "quantity": h.quantity,
            "avg_buy_price": h.avg_buy_price,
            "asset_type": h.asset_type or "STOCK",
            "sector": h.sector or "Other",
            "status": "REALIZED",
            "current_price": h.current_price or h.avg_buy_price,
            "sell_price": h.sell_price or 0.0,
            "realized_pnl": realized_pnl or 0.0,
            "value": 0.0,
            "portfolio_weight": 0.0,
            "fresh": True
        })

    return {
        "enriched_holdings": enriched,
        "macro_context": {},
        "errors": errors,
        "current_node": "enricher"
    }
