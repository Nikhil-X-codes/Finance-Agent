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

        SECTOR_CLASSIFICATION_PROMPT = """Classify each holding into exactly one sector using the rules below.

STOCK SECTOR RULES (Indian market):
- Classify the security into its appropriate sector based on its full company name (e.g. "G M BREWERIES LTD" -> "Consumer Defensive", "TATA COMMUNICATIONS LTD" -> "Telecom") and ticker symbol using your general financial knowledge of Indian markets.
- Do NOT use a hardcoded lookup list of companies. Instead, analyze the semantic meaning of the name (e.g. names containing "Bank" -> "Banking", "Breweries" -> "Consumer Defensive", "Pharm" -> "Pharma", "Motors" -> "Automobile", "Steels" -> "Metals & Mining").
- Use standard Indian market sectors such as:
  * Banking
  * IT
  * Energy
  * Pharma
  * FMCG
  * Automobile
  * Metals & Mining
  * Telecom
  * Real Estate
  * Infrastructure
  * Specialty Chemicals
  * Financial Services
  * Defense
  * Consumer Defensive (including Breweries/Beverages)
  * Commodity
  * International
- Mutual fund sector: Classify based on the asset category mentioned in the scheme name or category (e.g., Large Cap, Mid Cap, Small Cap, ELSS/Tax Saver, Flexi Cap, Multi Cap, Hybrid, Debt, Gold).
- Do NOT classify a sector as "Unknown" if you can reasonably infer it from the name (e.g. GMBREW is G M Breweries, so it is "Consumer Defensive" or "Beverages").

Return ONLY the sector name, nothing else."""

        system_prompt = (
            "You are an expert financial document parser specializing in Indian broker statements "
            "(Groww, Zerodha, Upstox, ICICI Direct, HDFC Securities, Angel One, 5paisa, Motilal Oswal). "
            "Extract holdings and realized trades with precision.\n\n"
            "EXTRACTION RULES:\n"
            "- Extract ALL holdings and trades from the document, even if some fields are missing.\n"
            "- Use null for any field that is not present or unreadable in the document.\n"
            "- Do NOT fabricate ISINs, prices, or quantities that are not in the source document. "
            "If an ISIN is genuinely missing, generate a deterministic 12-character placeholder starting with INE "
            "(e.g., INE followed by 9 alphanumeric characters derived from the ticker).\n"
            "- If tables span multiple pages, treat them as a single continuous table.\n"
            "- If the document contains summary/total rows, use them to cross-validate individual row values.\n"
            "- Ticker symbols must be UPPERCASE and match NSE/BSE conventions.\n"
            "- Preserve exact numeric values — do NOT round prices, quantities, or P&L values.\n\n"
            f"{SECTOR_CLASSIFICATION_PROMPT}"
        )

        extracted = structured_llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Parse the following Indian broker statement. Extract all holdings (active positions) and realized trades (sold/closed positions). Preserve exact values from the document.\n\n{full_text}"}
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