"""Conditional edge functions and routing logic for the LangGraph pipeline."""

from __future__ import annotations

from typing import Any

from ..state import PortfolioState


def has_news(state: PortfolioState) -> bool:
    """Check if any holdings have recent news fetched."""
    enriched_holdings = state.get("enriched_holdings") or []
    return any(len(item.get("news") or []) > 0 for item in enriched_holdings)


def has_concentration_risk(state: PortfolioState) -> bool:
    """Check if any holding exceeds single stock concentration limits (default 15%)."""
    enriched_holdings = state.get("enriched_holdings") or []
    thresholds = state.get("dynamic_thresholds") or {}
    limit = thresholds.get("single_stock_max_pct", 0.15)
    return any(item.get("portfolio_weight", 0.0) > limit for item in enriched_holdings)


def has_sector_drift(state: PortfolioState) -> bool:
    """Check if any sector weight exceeds sector guidelines (default 30%)."""
    enriched_holdings = state.get("enriched_holdings") or []
    thresholds = state.get("dynamic_thresholds") or {}
    limit = thresholds.get("sector_max_pct", 0.30)
    
    sector_weights: dict[str, float] = {}
    for item in enriched_holdings:
        sec = item.get("sector") or "Unknown"
        sector_weights[sec] = sector_weights.get(sec, 0.0) + item.get("portfolio_weight", 0.0)
        
    return any(weight > limit for weight in sector_weights.values())


def has_high_expense_ratio(state: PortfolioState) -> bool:
    """Check if any mutual fund has expense ratio exceeding guideline limits (default 2.25%)."""
    enriched_holdings = state.get("enriched_holdings") or []
    thresholds = state.get("dynamic_thresholds") or {}
    limit = thresholds.get("mutual_fund_max_ter", 2.25)
    
    for item in enriched_holdings:
        if item.get("asset_type") == "MUTUAL_FUND":
            if float(item.get("expense_ratio") or 0.0) > limit:
                return True
    return False


def is_macro_sensitive(state: PortfolioState) -> bool:
    """Check if the portfolio contains interest-rate sensitive sectors and repo rate is high/changed."""
    macro_context = state.get("macro_context") or {}
    repo_rate = float(macro_context.get("repo_rate") or macro_context.get("policy_repo_rate") or 0.0)
    
    if repo_rate == 0.0:
        return False
        
    # Rate-sensitive sectors in India: Real Estate, Banking, NBFCs, Auto
    rate_sensitive_sectors = {"real estate", "banking", "finance", "nbfc", "auto", "automobile"}
    
    enriched_holdings = state.get("enriched_holdings") or []
    for item in enriched_holdings:
        sec = str(item.get("sector") or "").lower()
        if any(rss in sec for rss in rate_sensitive_sectors):
            return True
            
    return False


def route_recommender(state: PortfolioState) -> str:
    """Router edge to determine whether we skip the recommender node on severe parsing errors."""
    errors = state.get("errors") or []
    # If we have fatal parser or enricher errors that leave us with no holdings, go straight to output
    normalized = state.get("normalized_holdings") or []
    if not normalized:
        return "output"
    return "recommender"
