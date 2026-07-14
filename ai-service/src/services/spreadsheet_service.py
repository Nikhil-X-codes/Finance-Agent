"""Universal statement parser — works for any broker, any format."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
from langchain_groq import ChatGroq

from src.config.models import Holding, ParseStatementResponse, RealizedTrade
from src.config.settings import settings


class UniversalParser:
    """One parser for all brokers, all formats — no structured output."""

    def __init__(self):
        self.llm = ChatGroq(
            groq_api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            temperature=0.0,
            max_tokens=4096,
        )

    def parse(self, file_path: str) -> ParseStatementResponse:
        """Universal parse — works for any broker, any format."""

        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY required")

        # Stage 1: Extract raw tables as text
        tables_text = self._extract_tables_text(file_path)

        if not tables_text.strip():
            raise ValueError("Could not extract any content from file")

        # Stage 2: LLM parses as plain text (NO structured output)
        system_prompt = """You are an expert financial document parser specializing in Indian broker statements (Groww, Zerodha, Upstox, ICICI Direct, HDFC Securities, Angel One, 5paisa, Motilal Oswal).

Your task: Read the extracted tables and classify each data row as HOLDING, REALIZED_TRADE, or SKIP.

CLASSIFICATION RULES (follow strictly):
- HOLDING: Active position the investor currently owns. Indicators: quantity > 0, has current/closing/LTP price, NO sell date, NO sell price, status may say "Active" or "Open".
- REALIZED_TRADE: Position that has been sold/closed. Indicators: has sell date OR sell price OR realized P&L value, status may say "Sold", "Closed", "Executed", or "Completed".
- SKIP: Header rows, summary/total rows, charge/brokerage rows, empty rows, disclaimer text, footer rows.

DISAMBIGUATION (when a row could be either):
- If a row has BOTH a buy price AND a sell price → REALIZED_TRADE.
- If a row has quantity > 0 but NO sell price and NO sell date → HOLDING.
- If a row has quantity = 0 → SKIP (unless it has realized P&L, then REALIZED_TRADE with the original quantity).
- If the same ticker appears in multiple rows (different trade dates), keep them as SEPARATE rows — do NOT aggregate.

BROKER-SPECIFIC NOTES:
- Groww: Often shows trade-by-trade rows. "LTP" column = current price for holdings. "P&L" column = realized P&L for sold trades.
- Zerodha/Kite: Uses "Avg. cost" for buy price, "LTP" for current price. "P&L" = unrealized for holdings.
- Upstox: May use "Buy Avg" and "Sell Avg" columns. Presence of "Sell Avg" > 0 means REALIZED_TRADE.
- ICICI Direct/HDFC: May show ISIN in a separate column. "Net Qty" = current quantity.

For each valid row, output a JSON object with these exact fields:
{
  "row_type": "HOLDING" or "REALIZED_TRADE",
  "ticker": "stock ticker or fund code (NSE symbol preferred, uppercase)",
  "name": "full company/fund name exactly as shown in the document",
  "isin": "ISIN if present in the data, else empty string — do NOT fabricate ISINs",
  "quantity": number (must be > 0),
  "buy_price": number (average buy price, must be >= 0),
  "sell_price": number or null (only for REALIZED_TRADE),
  "buy_date": "YYYY-MM-DD" or null (extract from document if present),
  "sell_date": "YYYY-MM-DD" or null (only for REALIZED_TRADE),
  "realized_pnl": number or null (only for REALIZED_TRADE — use value from document, or calculate as (sell_price - buy_price) * quantity),
  "current_price": number or null (only for HOLDING — LTP/current/closing price),
  "asset_type": "STOCK" or "ETF" or "MUTUAL_FUND" or "BOND",
  "sector": "sector name"
}

ASSET TYPE RULES:
- ISIN starting with "INF" → MUTUAL_FUND
- Name contains "ETF", "BeES", "Nifty ETF", "Gold ETF" → ETF
- Name contains "Bond", "Debenture", "NCD" → BOND
- Everything else on NSE/BSE → STOCK

SECTOR CLASSIFICATION RULES (Indian market):
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

DATA INTEGRITY RULES:
- Preserve exact numeric values from the source document — do NOT round prices or quantities.
- If a field is missing or unreadable, use null — do NOT guess or fabricate values.
- Ticker symbols must be UPPERCASE and match NSE/BSE conventions.

OUTPUT FORMAT:
Return ONLY a JSON array. No markdown, no explanation, no code blocks, no preamble.
Example:
[
  {"row_type":"REALIZED_TRADE","ticker":"TATACOMM","name":"TATA COMMUNICATIONS LTD","isin":"INE151A01013","quantity":1,"buy_price":1850,"sell_price":1920,"buy_date":"2025-10-23","sell_date":"2025-11-04","realized_pnl":70,"current_price":null,"asset_type":"STOCK","sector":"Telecom"},
  {"row_type":"HOLDING","ticker":"GMBREW","name":"G M BREWERIES LTD","isin":"INE075D01018","quantity":1,"buy_price":1240,"sell_price":null,"buy_date":"2025-10-27","sell_date":null,"realized_pnl":null,"current_price":982.45,"asset_type":"STOCK","sector":"Consumer Defensive"}
]"""

        user_prompt = f"""Parse the following tables extracted from an Indian broker statement. Classify each row as HOLDING, REALIZED_TRADE, or SKIP.

{tables_text}

IMPORTANT:
- Return ONLY the JSON array of classified rows.
- Preserve all numeric values exactly as they appear in the source data.
- If the same stock appears in multiple rows (different trades), keep them as separate entries."""

        # Call LLM as plain text (NO structured output)
        response = self.llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        # Parse JSON from text response
        raw_rows = self._extract_json_array(response.content)

        # Detect broker name from table content
        broker_name = "UNKNOWN"
        tables_lower = tables_text.lower()
        if any(k in tables_lower for k in ["groww", "groww invest"]):
            broker_name = "Groww"
        elif any(k in tables_lower for k in ["zerodha", "kite"]):
            broker_name = "Zerodha"
        elif any(k in tables_lower for k in ["upstox", "rksv"]):
            broker_name = "Upstox"
        elif "icici" in tables_lower:
            broker_name = "ICICI Direct"
        elif "hdfc" in tables_lower:
            broker_name = "HDFC Securities"

        # Convert to models
        holdings = []
        realized_trades = []

        for row in raw_rows:
            if row.get("row_type") == "SKIP":
                continue

            ticker = str(row.get("ticker", "")).strip().upper()
            name = str(row.get("name", ticker)).strip()
            isin = str(row.get("isin", "")).strip().upper()
            qty = float(row.get("quantity", 0))
            buy_price = float(row.get("buy_price", 0))

            if row.get("row_type") == "HOLDING" and qty > 0:
                current_price = row.get("current_price")
                if current_price is not None:
                    current_price = float(current_price)
                else:
                    current_price = buy_price

                asset_type = str(row.get("asset_type", "STOCK")).upper()
                if asset_type not in {"STOCK", "ETF", "MUTUAL_FUND", "BOND"}:
                    asset_type = "MUTUAL_FUND" if isin.startswith("INF") else "STOCK"

                holdings.append(Holding(
                    isin=isin or self._generate_isin(ticker),
                    ticker=ticker,
                    name=name,
                    quantity=qty,
                    avg_buy_price=buy_price,
                    asset_type=asset_type,
                    sector=row.get("sector") or "Unknown",
                    status="UNREALIZED",
                    current_price=current_price,
                ))

            elif row.get("row_type") == "REALIZED_TRADE":
                sell_price = row.get("sell_price")
                sell_price = float(sell_price) if sell_price is not None else 0.0

                realized_pnl = row.get("realized_pnl")
                if realized_pnl is None:
                    realized_pnl = (sell_price - buy_price) * qty
                else:
                    realized_pnl = float(realized_pnl)

                realized_trades.append(RealizedTrade(
                    isin=isin or self._generate_isin(ticker),
                    ticker=ticker,
                    name=name,
                    quantity=qty,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    buy_date=row.get("buy_date"),
                    sell_date=row.get("sell_date"),
                    realized_pnl=realized_pnl,
                ))

        # Calculate summary
        realized_pnl_total = sum(t.realized_pnl or 0.0 for t in realized_trades)
        unrealized_pnl_total = sum(
            ((h.current_price or h.avg_buy_price) - h.avg_buy_price) * h.quantity
            for h in holdings
        )

        return ParseStatementResponse(
            broker_detected=broker_name,
            confidence=0.92,
            holdings=holdings,
            realized_trades=realized_trades,
            unrecognized_rows=[],
            summary={
                "realized_pnl": realized_pnl_total,
                "unrealized_pnl": unrealized_pnl_total,
                "active_holdings": len(holdings),
                "completed_trades": len(realized_trades),
            }
        )

    def _extract_tables_text(self, file_path: str) -> str:
        """Extract ALL tables as plain text from any file."""
        suffix = Path(file_path).suffix.lower()
        sections = []

        if suffix == ".csv":
            df = pd.read_csv(file_path)
            sections.append(f"=== CSV FILE ===\nColumns: {', '.join(df.columns.tolist())}\n")
            sections.append(df.head(20).to_string())
            sections.append(f"\n... ({len(df)} total rows)")

        elif suffix in (".xlsx", ".xls"):
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
            xls = pd.ExcelFile(file_path, engine=engine)
            try:
                for sheet_name in xls.sheet_names:
                    try:
                        df = pd.read_excel(xls, sheet_name, header=None)
                        if df.empty or df.isna().all().all():
                            continue

                        # Try to find header row
                        header_row = 0
                        for i in range(min(5, len(df))):
                            row_text = " ".join([str(v) for v in df.iloc[i].values if not pd.isna(v)])
                            if any(k in row_text.lower() for k in
                                   ["isin", "symbol", "stock", "quantity", "price", "name"]):
                                header_row = i
                                break

                        # Re-read with detected header — use file_path, NOT xls,
                        # so pandas opens its own handle
                        df_parsed = pd.read_excel(
                            file_path, sheet_name=sheet_name,
                            header=header_row, engine=engine
                        )

                        sections.append(f"\n=== SHEET: {sheet_name} ===")
                        sections.append(f"Columns: {', '.join([str(c) for c in df_parsed.columns.tolist()])}")
                        sections.append(df_parsed.head(15).to_string())
                        if len(df_parsed) > 15:
                            sections.append(f"... ({len(df_parsed)} total rows)")
                    except Exception as e:
                        sections.append(f"\n=== SHEET: {sheet_name} === (Error: {e})")
            finally:
                # IMPORTANT: Close the file so Windows can delete it later
                xls.close()

        return "\n".join(sections)

    def _extract_json_array(self, text: str) -> list[dict]:
        """Extract JSON array from LLM response text."""
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first ``` line
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove last ``` line
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Remove "json" prefix if present
        if text.lower().startswith("json"):
            text = text[4:].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find array in text using regex
            match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            # Return empty if all fails
            print(f"Warning: Failed to parse LLM JSON output: {text[:200]}...")
            return []

    def _generate_isin(self, ticker: str) -> str:
        """Generate deterministic placeholder ISIN."""
        h = hashlib.md5(ticker.encode()).hexdigest()[:9].upper()
        return f"INE{h}"


# ==================== SERVICE INTERFACE ====================

class SpreadsheetService:
    """Backward-compatible service wrapper."""

    def __init__(self):
        self.parser = UniversalParser()

    def parse_statement(self, file_path: str) -> ParseStatementResponse:
        """Parse any statement file."""
        return self.parser.parse(file_path)