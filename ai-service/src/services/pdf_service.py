"""Broker detection and PDF statement extraction using LangChain and Groq."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_community.document_loaders import PyPDFLoader
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from src.config.models import Holding, ParseStatementResponse, RealizedTrade
from src.config.settings import settings


class ExtractedHolding(BaseModel):
    isin: str = Field(description="12-character ISIN (e.g. INE002A01018). If missing or not present in the document, generate a deterministic 12-character placeholder ISIN starting with INE based on the ticker/symbol.")
    ticker: str = Field(description="Stock ticker symbol or mutual fund scheme code")
    name: str = Field(description="Name of the security or mutual fund scheme")
    quantity: float = Field(description="Quantity held, must be > 0")
    avg_buy_price: float = Field(description="Average buy price or acquisition cost, must be >= 0")
    asset_type: str = Field(description="Asset type. Must be: STOCK, MUTUAL_FUND, ETF, or BOND.")
    sector: str = Field(description="Classified sector based on ticker/scheme name")


class ExtractedRealizedTrade(BaseModel):
    isin: str = Field(description="12-character ISIN. If missing or not present in the document, generate a deterministic 12-character placeholder ISIN starting with INE based on the ticker/symbol.")
    ticker: str = Field(description="Stock ticker or mutual fund scheme code")
    name: str = Field(description="Name of the security")
    quantity: float = Field(description="Quantity sold/traded, must be > 0")
    buy_price: float = Field(description="Purchase/acquisition price, must be >= 0")
    sell_price: float = Field(description="Selling price, must be >= 0")
    buy_date: str | None = Field(None, description="Date of purchase (YYYY-MM-DD)")
    sell_date: str | None = Field(None, description="Date of sale (YYYY-MM-DD)")
    realized_pnl: float | None = Field(None, description="Realized profit or loss")


class StatementExtraction(BaseModel):
    broker_detected: str = Field(description="Name of the broker, e.g. Zerodha, Groww, Upstox, ICICI Direct, HDFC Securities, or UNKNOWN")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    holdings: list[ExtractedHolding] = Field(default_factory=list, description="List of current/active holdings")
    realized_trades: list[ExtractedRealizedTrade] = Field(default_factory=list, description="List of realized trades")
    unrecognized_rows: list[dict[str, Any]] = Field(default_factory=list, description="List of unrecognized/skipped rows")


class PDFService:
    def parse_statement(self, file_path: str) -> ParseStatementResponse:
        """Parse a PDF broker statement using PyPDFLoader and ChatGroq."""
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set in settings")

        path = Path(file_path)
        loader = PyPDFLoader(str(path))
        docs = loader.load()

        full_text = "\n".join([doc.page_content for doc in docs])
        if not full_text.strip():
            raise ValueError("Could not extract text from PDF")

        llm = ChatGroq(
            groq_api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            temperature=0.0
        )
        structured_llm = llm.with_structured_output(StatementExtraction)

        SECTOR_CLASSIFICATION_PROMPT = """Classify each holding into exactly one sector.

STOCK sectors:
- BANKING (HDFCBANK, ICICIBANK, SBIN, AXISBANK, KOTAKBANK)
- IT / TECHNOLOGY (INFY, TCS, WIPRO, HCLTECH, TECHM)
- ENERGY / OIL (RELIANCE, ONGC, NTPC, POWERGRID, COALINDIA)
- PHARMA (SUNPHARMA, DRREDDY, CIPLA, DIVISLAB, BIOCON)
- FMCG (ITC, HINDUNILVR, NESTLE, BRITANNIA, DABUR)
- AUTOMOBILE (TATAMOTORS, MARUTI, M&M, EICHERMOT, BAJAJ-AUTO)
- METALS / MINING (TATASTEEL, JSWSTEEL, HINDALCO, COALINDIA)
- TELECOM (BHARTIARTL, IDEA, RCOM)
- REAL ESTATE (DLF, OBEROIRLTY, GODREJPROP)
- INFRASTRUCTURE / CONSTRUCTION (LT, ADANIPORTS, DMART)
- CHEMICALS (UPL, PIIND, SRF, DEEPAKNTR)
- FINANCIAL SERVICES (BAJFINANCE, HDFCLIFE, ICICIPRULI, SBILIFE)

MUTUAL FUND sectors (by category):
- EQUITY_LARGE_CAP → Large Cap
- EQUITY_MID_CAP → Mid Cap  
- EQUITY_SMALL_CAP → Small Cap
- EQUITY_ELSS → Tax Saver (80C)
- EQUITY_SECTORAL → Thematic/Sectoral
- EQUITY_FLEXI_CAP → Flexi Cap
- EQUITY_MULTI_CAP → Multi Cap
- DEBT → Debt/Bonds
- HYBRID → Hybrid
- GOLD → Gold
- INDEX → Index Fund

Rules:
1. Use ticker symbol to determine stock sector
2. Use scheme name/category for MF sector
3. If uncertain, use "Other"
4. Gold ETFs/Funds → "Gold"
5. International Funds → "International"

Return ONLY the sector name, nothing else."""

        system_prompt = (
            "You are an expert financial document parser. Extract the holdings and realized trades "
            "from the broker statement document. Ensure you capture ISINs, tickers, names, "
            "quantities, and average prices. Do not invent information. If an ISIN is missing, "
            "generate a deterministic 12-character placeholder ISIN starting with INE (e.g. INE followed by "
            "9 alphanumeric characters derived from the ticker/symbol).\n\n"
            f"{SECTOR_CLASSIFICATION_PROMPT}"
        )

        extracted = structured_llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Parse the following broker statement:\n\n{full_text}"}
        ])

        holdings = []
        for h in extracted.holdings:
            ticker = h.ticker.strip().upper()
            isin = h.isin.strip().upper()
            asset_type = h.asset_type.upper()
            if asset_type not in {"STOCK", "MUTUAL_FUND", "ETF", "BOND"}:
                asset_type = "MUTUAL_FUND" if isin.startswith("INF") else "STOCK"

            holdings.append(Holding(
                isin=isin,
                ticker=ticker,
                name=h.name or ticker,
                quantity=h.quantity,
                avg_buy_price=h.avg_buy_price,
                asset_type=asset_type,
                sector=h.sector
            ))

        realized_trades = []
        for r in extracted.realized_trades:
            ticker = r.ticker.strip().upper()
            isin = r.isin.strip().upper()
            realized_trades.append(RealizedTrade(
                isin=isin,
                ticker=ticker,
                name=r.name or ticker,
                quantity=r.quantity,
                buy_price=r.buy_price,
                sell_price=r.sell_price,
                buy_date=r.buy_date,
                sell_date=r.sell_date,
                realized_pnl=r.realized_pnl
            ))

        return ParseStatementResponse(
            broker_detected=extracted.broker_detected or "UNKNOWN",
            confidence=extracted.confidence,
            holdings=holdings,
            realized_trades=realized_trades,
            unrecognized_rows=extracted.unrecognized_rows,
            summary={
                "total_holdings": len(holdings),
                "total_realized_trades": len(realized_trades),
                "total_unrecognized": len(extracted.unrecognized_rows),
            } if (realized_trades or extracted.unrecognized_rows) else None,
        )