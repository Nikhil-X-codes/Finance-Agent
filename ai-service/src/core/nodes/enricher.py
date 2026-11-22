"""Fetch the public market context displayed in the portfolio report."""

import asyncio

from src.config.models import Holding
from src.core.tools.mf_tools import get_metadata
from src.core.tools.news_tools import get_stock_news
from src.core.tools.stock_tools import get_fundamentals
from src.services.market_data import market_data

from ..state import ReportState


async def _enrich_holding(holding: Holding, include_news: bool) -> dict:
    row = holding.model_dump(mode="json")
    if holding.status == "REALIZED" or holding.quantity == 0:
        return row

    if holding.asset_type in {"STOCK", "ETF"}:
        quote_task = market_data.quote(holding.ticker)
        if include_news:
            quote, news = await asyncio.gather(
                quote_task, get_stock_news(holding.ticker, holding.name), return_exceptions=True,
            )
            if not isinstance(news, Exception):
                row["news"] = news.data.get("news", [])
        else:
            quote, = await asyncio.gather(quote_task, return_exceptions=True)

        if isinstance(quote, dict) and quote.get("current_price") is not None:
            row["market_quote"] = quote["current_price"]
            row["market_quote_as_of"] = quote.get("timestamp")
            row["market_quote_source"] = quote.get("source")
            row["market_quote_status"] = quote.get("status")

        if not holding.sector:
            result, = await asyncio.gather(get_fundamentals(holding.ticker), return_exceptions=True)
            if not isinstance(result, Exception):
                row["sector"] = result.data.get("sector")
    elif holding.asset_type == "MUTUAL_FUND" and holding.isin and not holding.sector:
        result, = await asyncio.gather(get_metadata(holding.isin), return_exceptions=True)
        if not isinstance(result, Exception):
            row["sector"] = result.data.get("category")

    return row


async def enrich_portfolio(state: ReportState) -> dict:
    holdings = state.get("normalized_holdings", [])
    include_news = state.get("include_news", True)
    report_rows = asyncio.gather(*(_enrich_holding(holding, include_news) for holding in holdings))

    if include_news and holdings:
        rows, market_news = await asyncio.gather(
            report_rows, get_stock_news("NIFTY", "Indian Share Market"), return_exceptions=True,
        )
        return {
            "enriched_holdings": rows if isinstance(rows, list) else [h.model_dump(mode="json") for h in holdings],
            "market_news": market_news.data.get("news", []) if not isinstance(market_news, Exception) else [],
        }

    return {"enriched_holdings": await report_rows, "market_news": []}
