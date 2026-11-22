"""API routes for the AI service."""

from fastapi import APIRouter

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
