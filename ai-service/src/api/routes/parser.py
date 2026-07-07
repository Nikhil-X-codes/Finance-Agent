"""Statement parsing API routes."""

import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile, HTTPException

from src.services.pdf_service import PDFService
from src.services.spreadsheet_service import SpreadsheetService

router = APIRouter()


def calculate_sector_allocation(holdings: list[Any]) -> dict[str, float]:
    """Calculate percentage allocation by sector based on holding value."""
    sector_values = {}
    total_value = 0.0
    
    for h in holdings:
        price = h.avg_buy_price
        value = h.quantity * price
        total_value += value
        
        sector = h.sector or "Other"
        sector_values[sector] = sector_values.get(sector, 0.0) + value
        
    allocation = {}
    for sector, value in sector_values.items():
        allocation[sector] = round((value / total_value) * 100, 2) if total_value > 0.0 else 0.0
        
    return dict(sorted(allocation.items(), key=lambda x: x[1], reverse=True))


def _safe_remove(path: str, max_retries: int = 3):
    """Safely remove file with retries for Windows file-locking issues."""
    for i in range(max_retries):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            if i < max_retries - 1:
                time.sleep(0.5)  # Wait for file handle to be released
            else:
                print(f"Warning: Could not delete temp file {path}")


@router.post("/parse-statement")
async def parse_statement(
    file: UploadFile = File(..., description="Broker statement: PDF, XLSX, XLS, or CSV")
) -> Any:
    """Parse a broker statement and return holdings preview."""
    
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided. Use multipart/form-data with 'file' field.")
    
    filename = file.filename
    suffix = Path(filename).suffix.lower()
    allowed = {".pdf", ".xlsx", ".xls", ".csv"}
    
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: '{suffix}'. Allowed: {', '.join(sorted(allowed))}"
        )

    # Use NamedTemporaryFile with delete=False so we control cleanup
    temp_path = os.path.join(tempfile.gettempdir(), f"stmt-{uuid.uuid4().hex[:8]}{suffix}")

    try:
        content = await file.read()
        if not content or len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        with open(temp_path, "wb") as f:
            f.write(content)

        # Parse with appropriate service
        if suffix == ".pdf":
            service = PDFService()
            result = service.parse_statement(temp_path)
        else:
            service = SpreadsheetService()
            result = service.parse_statement(temp_path)

        # Build response
        return {
            "broker_detected": result.broker_detected,
            "confidence": result.confidence,
            "holdings": [
                {
                    "ticker": h.ticker,
                    "name": h.name,
                    "quantity": h.quantity,
                    "avg_buy_price": h.avg_buy_price,
                    "asset_type": h.asset_type,
                    "sector": h.sector,
                    "status": getattr(h, "status", "UNREALIZED"),
                    "current_price": getattr(h, "current_price", None),
                    "sell_price": getattr(h, "sell_price", None),
                    "realized_pnl": getattr(h, "realized_pnl", None),
                }
                for h in result.holdings
              ],
            "sector_allocation": calculate_sector_allocation(result.holdings),
            "realized_trades": [
                {
                    "isin": r.isin,
                    "ticker": r.ticker,
                    "name": r.name,
                    "quantity": r.quantity,
                    "buy_price": r.buy_price,
                    "sell_price": r.sell_price,
                    "buy_date": r.buy_date,
                    "sell_date": r.sell_date,
                    "realized_pnl": r.realized_pnl,
                }
                for r in getattr(result, "realized_trades", [])
            ],
            "unrecognized_rows": result.unrecognized_rows,
            "summary": getattr(result, "summary", None),
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Statement parsing failed: {str(e)}")
    finally:
      
        _safe_remove(temp_path)