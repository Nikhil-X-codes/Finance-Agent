"""Normalize validated holdings for report nodes."""

from ..state import ReportState


def parse_holdings(state: ReportState) -> dict:
    normalized = []
    for holding in state.get("raw_holdings", []):
        isin = (holding.isin or "").strip().upper()
        ticker = holding.ticker.strip().upper() or isin
        if not ticker:
            continue
        normalized.append(holding.model_copy(update={
            "ticker": ticker,
            "isin": isin or None,
            "asset_type": holding.asset_type or ("MUTUAL_FUND" if isin.startswith("INF") else "STOCK"),
            "status": holding.status or ("REALIZED" if holding.quantity == 0 else "UNREALIZED"),
        }))
    return {"normalized_holdings": normalized}
