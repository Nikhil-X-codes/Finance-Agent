"""Read all rows from CSV and Excel broker statements in bounded batches."""

import csv
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from xlrd.biffh import XLRDError

from src.config.models import ParseStatementResponse
from src.services.statement_extraction import parse_sections


def _sections(name: str, frame: pd.DataFrame) -> list[str]:
    rows = frame.dropna(how="all").fillna("").astype(str)
    chunks = []
    column_context = rows.iloc[:5].to_csv(index=False, header=False)
    for offset in range(0, len(rows), 100):
        block = rows.iloc[offset:offset + 100].to_csv(index=False, header=False)
        context = f"First rows for column and statement context only; extract records only from the next block:\n{column_context}\n" if offset else ""
        chunks.append(f"Sheet: {name}, rows {offset + 1} to {offset + len(rows.iloc[offset:offset + 100])}\n{context}{block}")
    return chunks


class SpreadsheetService:
    def parse_statement(self, file_path: str) -> ParseStatementResponse:
        suffix = Path(file_path).suffix.lower()
        try:
            if suffix == ".csv":
                with open(file_path, encoding="utf-8-sig", newline="") as stream:
                    frame = pd.DataFrame(list(csv.reader(stream, strict=True)))
                sections = _sections("CSV", frame.replace("", None))
            elif suffix in {".xlsx", ".xls"}:
                engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
                with pd.ExcelFile(file_path, engine=engine) as workbook:
                    sections = []
                    for sheet in workbook.sheet_names:
                        frame = workbook.parse(sheet, header=None, dtype=str)
                        sections.extend(_sections(sheet, frame))
            else:
                raise ValueError("Unsupported spreadsheet format.")
        except (ImportError, OSError, ValueError, csv.Error, BadZipFile, XLRDError) as exc:
            raise ValueError("Could not read the spreadsheet statement.") from exc
        return parse_sections(sections)
