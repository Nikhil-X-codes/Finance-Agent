"""Format shared portfolio facts for the report's advisory analysis."""

from src.services.portfolio_facts import invested_cost, is_active, summarize_portfolio

from ..state import ReportState


def _inr(value: float | None) -> str:
    return "unavailable" if value is None else f"INR {value:,.2f}"


def build_portfolio_context(state: ReportState) -> dict:
    holdings = [holding.model_dump(mode="json") for holding in state.get("normalized_holdings", [])]
    summary = summarize_portfolio(holdings)
    total_cost = summary["total_invested"]
    active_lines = []
    realized_lines = []
    for holding in holdings:
        if is_active(holding):
            weight = invested_cost(holding) / total_cost if total_cost else 0
            source = holding.get("price_source") or "source unknown"
            as_of = holding.get("price_as_of") or "date unknown"
            active_lines.append(
                f"- {holding['ticker']}: {holding['quantity']} units, average cost {_inr(holding['avg_buy_price'])}, "
                f"quote {_inr(holding.get('current_price'))} ({source}, {as_of}), invested cost weight {weight:.1%}."
            )
        elif holding.get("status") == "REALIZED":
            sold_on = holding.get("sell_date") or "an unknown date"
            realized_lines.append(
                f"- {holding['ticker']}: sold {holding['quantity']} units on {sold_on}, "
                f"sale price {_inr(holding.get('sell_price'))}, realized P&L {_inr(holding.get('realized_pnl'))}."
            )

    text = "\n".join([
        f"Invested cost: {_inr(total_cost)}",
        f"Quoted market value: {_inr(summary['total_current'])}",
        f"Unrealized P&L: {_inr(summary['unrealized_pnl'])}",
        f"Realized P&L: {_inr(summary['realized_pnl'])}",
        "Active holdings:", *(active_lines or ["No open positions."]),
        "Realized transactions:", *(realized_lines or ["No realized transactions."]),
    ])
    return {
        "portfolio_context_text": text if holdings else "No portfolio data available.",
        "portfolio_summary": summary,
    }
