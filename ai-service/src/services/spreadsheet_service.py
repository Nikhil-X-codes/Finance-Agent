"""Read all rows from CSV and Excel broker statements in bounded batches."""

import csv
from datetime import date
from pathlib import Path
import re
from zipfile import BadZipFile

import pandas as pd
from xlrd.biffh import XLRDError

from src.config.models import ParseStatementResponse
from src.services.statement_extraction import StatementExtraction, parse_sections, validate_extractions

ROWS_PER_BATCH = 16
MAX_SPREADSHEET_ROWS = 4000
HOLDING_COLUMNS = {
    "ticker": "ticker", "symbol": "ticker", "trading symbol": "ticker", "stock symbol": "ticker",
    "isin": "isin", "isin code": "isin",
    "name": "name", "company name": "name", "security name": "name", "stock name": "name",
    "quantity": "quantity", "qty": "quantity", "total quantity": "quantity",
    "average buy price": "avg_buy_price", "avg buy price": "avg_buy_price",
    "average price": "avg_buy_price", "avg price": "avg_buy_price",
    "current price": "current_price", "market price": "current_price", "ltp": "current_price",
    "last traded price": "current_price",
    "sector": "sector", "buy date": "buy_date", "asset type": "asset_type",
}
HOLDING_AUXILIARY_COLUMNS = {
    "exchange", "currency", "valuation date", "lot reference", "invested value",
    "invested amount", "current value", "market value", "unrealised p l", "unrealized p l",
    "unrealised p l pct", "unrealized p l pct", "unrealised p l percentage", "unrealized p l percentage",
}
HOLDING_TITLES = {"holdings", "holdings report", "holdings statement", "portfolio holdings"}
HOLDING_DATE_LABELS = {"as of", "holdings as of", "as on", "holdings as on"}


def _label(cell: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", cell.lower()))


def _holdings_table(frame: pd.DataFrame) -> StatementExtraction | None:
    """Read a single, unambiguous holdings table without calling the extraction model."""
    rows = frame.fillna("").astype(str)
    values = [[cell.strip() for cell in row] for row in rows.itertuples(index=False, name=None)]
    values = [row for row in values if any(row)]
    if not values:
        return StatementExtraction(confidence=1)

    coverage_end = None
    while values:
        preamble = [cell for cell in values[0] if cell]
        label = _label(preamble[0])
        if len(preamble) == 1 and label in HOLDING_TITLES:
            values.pop(0)
        elif len(preamble) == 2 and label in HOLDING_DATE_LABELS and coverage_end is None:
            try:
                coverage_end = date.fromisoformat(preamble[1].split(" ")[0])
            except ValueError:
                return None
            values.pop(0)
        else:
            break
    if not values:
        return None

    header, *records = values
    labels = [_label(cell.removesuffix("%").rstrip() + " pct" if cell.endswith("%") else cell) for cell in header]
    columns = [HOLDING_COLUMNS.get(label) for label in labels]
    fields = [column for column in columns if column]
    if (
        any(label and label not in HOLDING_COLUMNS and label not in HOLDING_AUXILIARY_COLUMNS for label in labels)
        or len(set(fields)) != len(fields)
        or not {"quantity", "avg_buy_price"}.issubset(fields)
        or not {"ticker", "isin"}.intersection(fields)
    ):
        return None

    holdings = []
    identity = columns.index("ticker") if "ticker" in columns else columns.index("isin")
    for row in records:
        if [_label(cell) for cell in row] == labels:
            return None
        if any(cell and not label for cell, label in zip(row, labels)):
            return None
        if _label(row[identity]) in {"total", "grand total"}:
            continue
        holdings.append({column: cell for column, cell in zip(columns, row) if column and cell})
    return StatementExtraction(confidence=1, coverage_end=coverage_end, holdings=holdings)


def _sections(name: str, frame: pd.DataFrame) -> list[str]:
    rows = frame.dropna(how="all").fillna("").astype(str)
    chunks = []
    column_context = rows.iloc[:5].to_csv(index=False, header=False)
    for offset in range(0, len(rows), ROWS_PER_BATCH):
        batch = rows.iloc[offset:offset + ROWS_PER_BATCH]
        block = batch.to_csv(index=False, header=False)
        context = f"First rows for column and statement context only; extract records only from the next block:\n{column_context}\n" if offset else ""
        chunks.append(f"Sheet: {name}, rows {offset + 1} to {offset + len(batch)}\n{context}{block}")
    return chunks


class SpreadsheetService:
    def parse_statement(self, file_path: str) -> ParseStatementResponse:
        suffix = Path(file_path).suffix.lower()
        try:
            if suffix == ".csv":
                with open(file_path, encoding="utf-8-sig", newline="") as stream:
                    frame = pd.DataFrame(list(csv.reader(stream, strict=True)))
                sheets = [("CSV", frame.replace("", None))]
            elif suffix in {".xlsx", ".xls"}:
                engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
                with pd.ExcelFile(file_path, engine=engine) as workbook:
                    sheets = [(sheet, workbook.parse(sheet, header=None, dtype=str)) for sheet in workbook.sheet_names]
            else:
                raise ValueError("Unsupported spreadsheet format.")
        except (ImportError, OSError, ValueError, csv.Error, BadZipFile, XLRDError) as exc:
            raise ValueError("Could not read the spreadsheet statement.") from exc
        parsed = [_holdings_table(frame) for _, frame in sheets]
        tables = [table for table in parsed if table is not None]
        if tables and len(tables) == len(sheets) and any(table.holdings for table in tables):
            if sum(len(table.holdings) for table in tables) > MAX_SPREADSHEET_ROWS:
                raise ValueError("Statement is too large to parse reliably. Upload a smaller statement.")
            return validate_extractions(tables)

        sections = [section for name, frame in sheets for section in _sections(name, frame)]
        return parse_sections(sections, max_sections=MAX_SPREADSHEET_ROWS // ROWS_PER_BATCH)
