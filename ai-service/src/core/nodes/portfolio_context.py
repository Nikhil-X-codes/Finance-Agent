"""Read the shared accounting facts for the report."""

from src.services.portfolio_facts import summarize_portfolio

from ..state import ReportState


def build_portfolio_context(state: ReportState) -> dict:
    holdings = [holding.model_dump(mode="json") for holding in state.get("normalized_holdings", [])]
    return {"portfolio_summary": summarize_portfolio(holdings)}
