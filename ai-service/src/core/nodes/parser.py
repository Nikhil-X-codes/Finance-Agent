"""Parser node for normalizing holdings and merging trade logs."""

from __future__ import annotations

import sqlite3
from typing import Any

from src.config.models import Holding
from src.config.settings import settings
from ..state import PortfolioState


def parse_holdings(state: PortfolioState) -> dict[str, Any]:
    """Normalize input holdings and merge manual trade logs from SQLite."""
    user_id = state.get("user_id", "")
    raw_holdings = state.get("raw_holdings") or []
    
    # 1. Normalize raw holdings to Holding Pydantic models
    normalized: list[Holding] = []
    errors: list[dict[str, str]] = list(state.get("errors") or [])
    
    for i, raw in enumerate(raw_holdings):
        try:
            # Map ticker or symbol to ISIN
            ticker = str(raw.get("ticker") or raw.get("symbol") or "").strip().upper()
            isin = str(raw.get("isin") or "").strip()
            
            # Auto-resolve ISIN if missing
            if not isin and ticker:
                isin = ticker
            
            if not isin:
                errors.append({
                    "code": "ISIN_RESOLUTION_FAILED",
                    "message": f"Could not resolve ISIN for ticker/symbol '{ticker}' at index {i}"
                })
                continue
            
            # Determine asset type (INF prefix is Mutual Fund, otherwise Stock)
            asset_type = "MUTUAL_FUND" if isin.startswith("INF") else "STOCK"
            
            # Build Holding object
            holding = Holding(
                isin=isin,
                ticker=ticker or isin,
                name=raw.get("name") or raw.get("schemeName") or ticker or isin,
                quantity=float(raw.get("quantity") or 0),
                avg_buy_price=float(raw.get("avg_buy_price") or raw.get("avg_price") or 0),
                asset_type=asset_type,
                sector=raw.get("sector"),
                status=raw.get("status") or ("REALIZED" if float(raw.get("quantity") or 0) == 0 else "UNREALIZED"),
                current_price=float(raw.get("current_price")) if raw.get("current_price") is not None else None,
                sell_price=float(raw.get("sell_price")) if raw.get("sell_price") is not None else None,
                realized_pnl=float(raw.get("realized_pnl")) if raw.get("realized_pnl") is not None else None,
            )
            normalized.append(holding)
        except Exception as e:
            errors.append({
                "code": "HOLDING_PARSING_FAILED",
                "message": f"Error parsing holding at index {i}: {str(e)}"
            })

    # 2. Merge Trade Log from SQLite
    merged_holdings = merge_trades(normalized, user_id, settings.sqlite_path)

    return {
        "normalized_holdings": merged_holdings,
        "errors": errors,
        "current_node": "parser"
    }


def merge_trades(holdings: list[Holding], user_id: str, sqlite_path: str) -> list[Holding]:
    """Merge newer trade logs from SQLite db into normalized holdings."""
    if not user_id:
        return holdings

    try:
        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()
        
        # Check if trades table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if not cursor.fetchone():
            conn.close()
            return holdings

        # Query trades for user
        cursor.execute(
            "SELECT ticker, transaction_type, quantity, price, date FROM trades WHERE user_id = ? ORDER BY date ASC",
            (user_id,)
        )
        trades = cursor.fetchall()
        conn.close()
        
        if not trades:
            return holdings

        # Index holdings by ticker/isin
        holdings_map = {h.isin: h for h in holdings}
        ticker_to_isin = {h.ticker: h.isin for h in holdings}
        
        for ticker, tx_type, qty, price, dt in trades:
            ticker = ticker.upper()
            isin = ticker_to_isin.get(ticker)
            
            if not isin:
                isin = ticker

            if isin in holdings_map:
                h = holdings_map[isin]
                if tx_type == "BUY":
                    # Weighted average buy price update
                    total_cost = (h.quantity * h.avg_buy_price) + (qty * price)
                    h.quantity += qty
                    if h.quantity > 0:
                        h.avg_buy_price = total_cost / h.quantity
                elif tx_type == "SELL":
                    h.quantity = max(0.0, h.quantity - qty)
                    if h.quantity == 0.0:
                        h.status = "REALIZED"
            else:
                # Add new holding if it was a buy
                if tx_type == "BUY" and qty > 0:
                    asset_type = "MUTUAL_FUND" if isin.startswith("INF") else "STOCK"
                    new_holding = Holding(
                        isin=isin,
                        ticker=ticker,
                        name=ticker,
                        quantity=qty,
                        avg_buy_price=price,
                        asset_type=asset_type,
                        status="UNREALIZED",
                    )
                    holdings_map[isin] = new_holding
                    ticker_to_isin[ticker] = isin

        # Filter out zeroed holdings ONLY if they are not explicitly marked as REALIZED or have realized_pnl
        return [h for h in holdings_map.values() if h.quantity > 0 or h.status == "REALIZED" or h.realized_pnl is not None]
        
    except Exception as e:
        print(f"Warning: Failed to merge trade logs: {e}")
        return holdings
