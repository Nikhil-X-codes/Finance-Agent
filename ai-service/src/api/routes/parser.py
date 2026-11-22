"""Statement parsing API routes."""

import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from src.config.settings import settings
from src.services.pdf_service import PDFService
from src.services.spreadsheet_service import SpreadsheetService
from src.services.statement_extraction import StatementExtractionError

router = APIRouter()
logger = logging.getLogger(__name__)
ALLOWED_SUFFIXES = {".pdf", ".xlsx", ".xls", ".csv"}


@router.post("/parse-statement")
async def parse_statement(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail="Upload a PDF, XLSX, XLS, or CSV statement.")

    data = await file.read(settings.max_pdf_size_bytes + 1)
    if not data or len(data) > settings.max_pdf_size_bytes:
        raise HTTPException(status_code=413, detail="Statement is empty or exceeds the upload limit.")

    with tempfile.TemporaryDirectory(prefix="finance-statement-") as directory:
        path = os.path.join(directory, f"statement{suffix}")
        try:
            with open(path, "wb") as stream:
                stream.write(data)
            service = PDFService() if suffix == ".pdf" else SpreadsheetService()
            result = await run_in_threadpool(service.parse_statement, path)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except StatementExtractionError as exc:
            logger.warning("Statement extraction failed (format=%s, reason=%s)", suffix, exc.code)
            raise HTTPException(status_code=503, detail="Statement extraction is temporarily unavailable.") from exc
        except Exception as exc:
            logger.warning(
                "Statement extraction failed (format=%s, error=%s, status=%s)",
                suffix, type(exc).__name__, getattr(exc, "status_code", None),
            )
            raise HTTPException(status_code=503, detail="Statement extraction is temporarily unavailable.") from exc

    payload = result.model_dump(mode="json")
    sector_costs: dict[str, float] = {}
    for holding in result.holdings:
        sector = holding.sector or "Other"
        sector_costs[sector] = sector_costs.get(sector, 0) + holding.avg_buy_price * holding.quantity
    total = sum(sector_costs.values())
    payload["sector_allocation"] = {sector: round(100 * cost / total, 2) for sector, cost in sector_costs.items()} if total else {}
    return payload
