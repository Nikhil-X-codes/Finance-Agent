"""Fetch public market context for the portfolio report."""

import asyncio
from datetime import datetime, timezone
import re

from src.config.models import Holding
from src.core.tools.mf_tools import get_metadata
from src.core.tools.news_tools import NewsResult, get_stock_news, select_report_news
from src.services.market_data import market_data
from src.services.portfolio_facts import invested_cost, is_active

from ..state import ReportState


async def _enrich_holding(holding: Holding) -> dict:
    row = holding.model_dump(mode="json")
    if not is_active(row):
        return row

    if holding.asset_type in {"STOCK", "ETF"}:
        if holding.ticker != holding.isin and re.fullmatch(r"[A-Z0-9][A-Z0-9&.\-]{0,19}", holding.ticker):
            quote = await market_data.quote(holding.ticker)
            if quote.get("current_price") is not None:
                row.update({
                    "market_quote": quote["current_price"],
                    "market_quote_as_of": quote.get("timestamp"),
                    "market_quote_source": quote.get("source"),
                    "market_quote_status": quote.get("status"),
                })
    elif holding.asset_type == "MUTUAL_FUND" and holding.isin and not holding.sector:
        result = await get_metadata(holding.isin)
        row["fund_category"] = result.data.get("category")

    return row


async def enrich_portfolio(state: ReportState) -> dict:
    holdings = state.get("normalized_holdings", [])
    records = [holding.model_dump(mode="json") for holding in holdings]
    active = [row for row in records if is_active(row)]
    enrichment = asyncio.gather(*(_enrich_holding(holding) for holding in holdings), return_exceptions=True)

    names = {}
    costs = {}
    for row in active:
        if row["asset_type"] == "STOCK":
            ticker = row["ticker"]
            names.setdefault(ticker, row["name"])
            costs[ticker] = costs.get(ticker, 0) + invested_cost(row)
    ranked = sorted(costs, key=costs.__getitem__, reverse=True)[:5]
    news_targets = [(ticker, names[ticker]) for ticker in ranked] + [("MARKET", None)] if active and state.get("include_news", True) else []
    news_requests = asyncio.gather(
        *(get_stock_news(ticker, name) for ticker, name in news_targets), return_exceptions=True,
    )
    if any(row["asset_type"] in {"STOCK", "ETF"} for row in active):
        rows, news, index = await asyncio.gather(enrichment, news_requests, market_data.index_snapshot(), return_exceptions=True)
    else:
        rows, news = await asyncio.gather(enrichment, news_requests)
        index = {}
    batches = {
        ticker: result.data.get("news", [])
        for (ticker, _), result in zip(news_targets, news)
        if isinstance(result, NewsResult)
    }
    return {
        "enriched_holdings": [row if isinstance(row, dict) else original for row, original in zip(rows, records)],
        "report_news": select_report_news(batches, datetime.now(timezone.utc)),
        "market_snapshot": index if isinstance(index, dict) else {},
    }
