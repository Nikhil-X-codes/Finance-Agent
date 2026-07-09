"""API routes for the AI service."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from src.config.models import EnrichRequest
from src.core.tools.news_tools import get_stock_news
from src.core.tools.stock_tools import get_fundamentals, get_quote

# Import sub-routers
from .parser import router as parser_router
from .report import router as report_router
from .qa import router as qa_router
from .trade import router as trade_router
from .mf_comparison import router as mf_comparison_router
from .stocks import router as stocks_router
from .portfolio import router as portfolio_router

router = APIRouter()

# Include sub-routers into the main router
router.include_router(parser_router)
router.include_router(report_router)
router.include_router(qa_router)
router.include_router(trade_router)
router.include_router(mf_comparison_router)
router.include_router(stocks_router, prefix="/v1")
router.include_router(portfolio_router)


def _stock_view(result_data: dict[str, object]) -> dict[str, object]:
    return {
        "ticker": result_data.get("ticker"),
        "current_price": result_data.get("current_price"),
        "day_change": result_data.get("day_change"),
        "source": result_data.get("source"),
        "cached": result_data.get("cached", False),
        "fresh": result_data.get("fresh", True),
    }


@router.post("/v1/enrich")
async def enrich(payload: EnrichRequest) -> dict:
    errors: list[dict[str, str]] = []
    stocks: list[dict[str, object]] = []
    mutual_funds: list[dict[str, object]] = []
    news: list[dict[str, object]] = []

    if payload.macro_only:
        return {"stocks": stocks, "mutual_funds": mutual_funds, "news": news, "macro": {}, "errors": errors}

    stock_results = await asyncio.gather(*(get_quote(ticker) for ticker in payload.tickers), return_exceptions=True)
    for ticker, result in zip(payload.tickers, stock_results):
        if isinstance(result, Exception):
            errors.append({"code": "STOCK_UNAVAILABLE", "message": str(result)})
            continue
        if result.data.get("error"):
            errors.append({"code": str(result.data.get("error")), "message": f"Stock data unavailable for {ticker}"})
            continue
        stocks.append(_stock_view(result.data))

    if payload.include_news:
        news_results = await asyncio.gather(*(get_stock_news(ticker) for ticker in payload.tickers), return_exceptions=True)
        for ticker, result in zip(payload.tickers, news_results):
            if isinstance(result, Exception):
                errors.append({"code": "NEWS_UNAVAILABLE", "message": str(result)})
                continue
            if result.data.get("error"):
                errors.append({"code": str(result.data.get("error")), "message": f"News unavailable for {ticker}"})
                continue
            for article in result.data.get("news", []):
                if isinstance(article, dict):
                    news.append(article)

    macro = {}

    return {"stocks": stocks, "mutual_funds": mutual_funds, "news": news, "macro": macro, "errors": errors}
