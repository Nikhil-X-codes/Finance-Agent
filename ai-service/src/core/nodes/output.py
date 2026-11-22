"""Render the saved report JSON and its Markdown view."""

from collections import Counter
from datetime import datetime, timezone
import re
import uuid
from typing import Any
from urllib.parse import quote

from src.services.portfolio_facts import invested_cost, is_active

from ..state import ReportState

MANDATORY_DISCLAIMER = (
    "For educational and informational purposes only. This report does not constitute financial, "
    "legal, or investment advice. Consult a qualified financial adviser for personal investment decisions."
)


def format_output(state: ReportState) -> dict[str, Any]:
    holdings = state.get("enriched_holdings") or []
    active = [holding for holding in holdings if is_active(holding)]
    realized = [holding for holding in holdings if holding.get("status") == "REALIZED"]
    facts = state.get("portfolio_summary") or {}
    sectors: dict[str, float] = {}
    for name, weight in facts.get("sector_weights", {}).items():
        label = "Unknown" if name.strip().casefold() in {"", "other", "unknown"} else name
        sectors[label] = sectors.get(label, 0) + weight
    concentration = state.get("concentration") or {}
    duplicate_candidates = Counter(
        (row.get("isin") or row["ticker"], row["quantity"], row["avg_buy_price"],
         row.get("sell_price"), row.get("realized_pnl"), row.get("buy_date"), row.get("sell_date"))
        for row in realized
    )
    invested = facts.get("total_invested", 0)
    report = {
        "id": f"rpt_{uuid.uuid4().hex[:12]}",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "generatedVia": state.get("generated_via", "RULE_BASED"),
        "portfolioSummary": {
            "totalValue": invested,
            "investedCost": invested,
            "marketValue": facts.get("total_current"),
            "unrealizedPnl": facts.get("unrealized_pnl"),
            "holdingsCount": len({row["ticker"] for row in active}),
            "overallRiskLevel": state.get("overall_risk", "UNAVAILABLE"),
            "sectorAllocation": {name: round(weight, 4) for name, weight in sectors.items()},
            "totalRealizedPnl": facts.get("realized_pnl"),
            "realizedTradeCount": len(realized),
            "pricedHoldings": sum(row.get("current_price") is not None for row in active),
            "activePositions": len(active),
            **concentration,
        },
        "riskFlags": [{
            "ticker": flag["ticker"], "flagType": flag["flag_type"], "severity": flag["severity"],
            "portfolioWeight": round(flag["portfolio_weight"], 4), "evidenceText": flag["evidence_text"],
            "citation": flag["citation"],
        } for flag in state.get("risk_flags") or []],
        "recommendations": state.get("recommendations") or [],
        "tradeHistory": [{
            "ticker": row["ticker"], "name": row.get("name"), "quantity": row["quantity"],
            "avgBuyPrice": row["avg_buy_price"], "sellPrice": row.get("sell_price"),
            "realizedPnl": row.get("realized_pnl"), "sellDate": row.get("sell_date"),
        } for row in realized],
        "possibleDuplicateTradeGroups": sum(count > 1 for count in duplicate_candidates.values()),
        "liveNews": state.get("report_news") or [],
        "newsIncluded": state.get("include_news", True),
        "marketSnapshot": state.get("market_snapshot") or {},
        "disclaimer": MANDATORY_DISCLAIMER,
    }
    report["markdown"] = render_report_markdown(report, active)
    return {"report_json": report}


def _currency(value: float | None) -> str:
    return "Unavailable" if value is None else f"INR {value:,.2f}"


def _text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return re.sub(r"([\\\x60*_\[\]<>|])", r"\\\1", text)


def render_report_markdown(report: dict[str, Any], active_holdings: list[dict[str, Any]]) -> str:
    summary = report["portfolioSummary"]
    risk = summary["overallRiskLevel"]
    as_of = datetime.fromisoformat(report["createdAt"]).strftime("%d %b %Y, %H:%M UTC")
    total = summary["investedCost"]
    coverage = summary.get("sectorCoverage")
    lines = [
        "# Portfolio Advisory Report", "", f"*Generated {as_of}*", "",
        "## Portfolio at a glance", "",
        f"- **Invested cost:** {_currency(total)}",
        f"- **Quoted market value:** {_currency(summary['marketValue'])}",
        f"- **Unrealized P&L:** {_currency(summary['unrealizedPnl'])}",
        f"- **Realized P&L:** {_currency(summary['totalRealizedPnl'])}",
        f"- **Concentration level:** {risk}",
        f"- **Statement quote coverage:** {summary['pricedHoldings']} of {summary['activePositions']} active positions",
    ]
    if summary.get("topTwoWeight") is not None:
        leaders = " and ".join(_text(row["ticker"]) for row in summary["largestHoldings"])
        lines.append(f"- **Two largest holdings:** {leaders} account for {summary['topTwoWeight']:.1%} of invested cost.")
    if coverage is not None:
        lines.append(f"- **Known sector coverage:** {coverage:.1%} of invested cost.")
        if coverage < 1:
            lines.append("- Sector concentration is only assessed for positions with a known classification.")

    lines.extend([
        "", "## Holdings and allocation", "",
        "| Holding | Type | Sector / fund category | Units | Average cost | Statement price/NAV | Quote date/source | Cost weight |",
        "|---|---|---|---:|---:|---:|---|---:|",
    ])
    for row in active_holdings:
        price = row.get("current_price")
        provenance = " / ".join(str(row.get(key) or "Unknown") for key in ("price_as_of", "price_source")) if price is not None else "Unavailable"
        weight = invested_cost(row) / total if total else 0
        category = row.get("sector") or row.get("fund_category") or "Unknown"
        if category.strip().casefold() in {"other", "unknown"}:
            category = "Unknown"
        lines.append(
            f"| {_text(row['ticker'])} | {_text(row.get('asset_type'))} | {_text(category)} | {row['quantity']:,} | "
            f"{_currency(row['avg_buy_price'])} | {_currency(price)} | {_text(provenance)} | {weight:.1%} |"
        )
    if summary["sectorAllocation"]:
        lines.extend(["", "### Invested cost by classification", ""])
        lines.extend(f"- {_text(name)}: {weight:.1%}" for name, weight in sorted(
            summary["sectorAllocation"].items(), key=lambda item: -item[1],
        ))

    lines.extend([
        "", "## Concentration and follow-up", "",
        "Concentration uses invested-cost weights. Holding thresholds are 25% for medium and 40% for high. "
        "Known sector thresholds are 45% and 60%. Volatility, liquidity, and suitability require additional data.",
    ])
    flags = report["riskFlags"]
    if flags:
        lines.extend(["", "| Level | Evidence |", "|---|---|"])
        lines.extend(
            f"| {flag['severity']} | {_text(flag['evidenceText'])} |"
            for flag in sorted(flags, key=lambda item: (item["severity"] != "HIGH", -item["portfolioWeight"]))
        )
    else:
        lines.extend(["", "Concentration could not be assessed." if risk == "UNAVAILABLE"
                      else "The available inputs did not trigger a concentration flag."])
    for item in report["recommendations"]:
        label = "Sector exposure" if item["action"] == "REVIEW_SECTOR" else _text(item["ticker"])
        lines.extend(["", f"- **Review {label}:** {_text(item['nextCheck'])}"])

    snapshot = report["marketSnapshot"]
    dated_quotes = [row for row in active_holdings if row.get("market_quote") is not None
                    and row.get("market_quote_source") and row.get("market_quote_as_of")]
    if snapshot or dated_quotes or report["newsIncluded"]:
        lines.extend(["", "## Public market context", ""])
    if snapshot:
        change = snapshot.get("dayChangePercent")
        move = f" ({change:+.2f}% for the session)" if change is not None else ""
        cached = " · cached" if snapshot.get("status") == "cached" else ""
        lines.extend([
            f"- **{_text(snapshot['name'])}:** {snapshot['value']:,.2f}{move} as of "
            f"{_text(snapshot['timestamp'])} · {_text(snapshot['source'])}{cached}.",
            "  The index snapshot is market context. Portfolio returns are measured separately.",
        ])
    if dated_quotes:
        lines.extend([
            "", "### Latest available public market quotes", "",
            "| Holding | Price | As of | Source | Status |", "|---|---:|---|---|---|",
        ])
        for row in dated_quotes:
            status = (row.get("market_quote_status") or "published").replace("_", " ")
            lines.append(
                f"| {_text(row['ticker'])} | {_currency(row['market_quote'])} | {_text(row['market_quote_as_of'])} | "
                f"{_text(row['market_quote_source'])} | {_text(status)} |"
            )
    if report["newsIncluded"]:
        lines.extend(["", "### Recent headlines", ""])
        if not report["liveNews"]:
            lines.append("No dated headlines from the last 30 days were available.")
        for article in report["liveNews"]:
            url = quote(article["url"], safe=":/?#[]@!$&'*+,;=%")
            published = datetime.fromisoformat(article["publishedAt"]).strftime("%d %b %Y")
            lines.append(
                f"- **{_text(article['ticker'])}** · [{_text(article['title'])}]({url}) · "
                f"{_text(article['source'])} · {published}"
            )

    if report["tradeHistory"]:
        lines.extend(["", "## Realized trades", ""])
        if report["possibleDuplicateTradeGroups"]:
            lines.append(
                f"**Review imported trade history.** {report['possibleDuplicateTradeGroups']} group(s) contain rows "
                "with matching trade details. The totals include all recorded trades pending your review."
            )
        lines.extend([
            "", "| Holding | Sold on | Units | Average cost | Sell price | Realized P&L |",
            "|---|---|---:|---:|---:|---:|",
        ])
        for trade in report["tradeHistory"]:
            lines.append(
                f"| {_text(trade['ticker'])} | {_text(trade['sellDate'] or 'Unknown')} | {trade['quantity']:,} | "
                f"{_currency(trade['avgBuyPrice'])} | {_currency(trade['sellPrice'])} | {_currency(trade['realizedPnl'])} |"
            )
    lines.extend(["", "---", "", MANDATORY_DISCLAIMER, ""])
    return "\n".join(lines)
