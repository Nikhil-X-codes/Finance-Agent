"""Portfolio report evidence and optional market context regressions."""

import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from src.config.models import Holding
from src.core.graph import create_report_graph
from src.core.nodes import recommender
from src.core.tools import nse_market
from src.core.tools.news_tools import select_report_news
from src.services.market_data import market_data


class ReportTests(unittest.TestCase):
    def test_report_accounts_for_missing_sectors_and_flags_repeated_trade_rows(self):
        holdings = [
            Holding(ticker="ONE", name="One", quantity=1, avg_buy_price=33, current_price=29),
            Holding(ticker="TWO", name="Two", quantity=1, avg_buy_price=28),
            Holding(ticker="THREE", name="Three", quantity=1, avg_buy_price=20, sector="Software"),
            Holding(ticker="FOUR", name="Four", quantity=1, avg_buy_price=19),
        ]
        closed = Holding(ticker="SOLD", name="Sold", quantity=1, avg_buy_price=10, sell_price=15,
                         realized_pnl=5, status="REALIZED", sell_date="2026-11-20")
        with (
            patch.object(market_data, "provider", None),
            patch.object(recommender, "settings", SimpleNamespace(groq_api_key="")),
        ):
            report = asyncio.run(create_report_graph().ainvoke({
                "raw_holdings": [*holdings, closed, closed], "include_news": False,
            }))["report_json"]
        summary = report["portfolioSummary"]
        self.assertEqual(summary["overallRiskLevel"], "MEDIUM")
        self.assertAlmostEqual(summary["topTwoWeight"], 0.61)
        self.assertAlmostEqual(summary["sectorCoverage"], 0.20)
        self.assertEqual(summary["sectorAllocation"], {"Unknown": 0.80, "Software": 0.20})
        self.assertEqual(summary["totalRealizedPnl"], 10)
        self.assertIsNone(summary["marketValue"])
        self.assertEqual(report["possibleDuplicateTradeGroups"], 1)
        self.assertEqual([item["action"] for item in report["recommendations"]], ["REVIEW_EXPOSURE"] * 2)
        self.assertIn("61.0% of invested cost", report["markdown"])
        self.assertNotIn("Recent headlines", report["markdown"])

    def test_model_only_supplies_review_explanations_for_real_flags(self):
        flags = [
            {"flag_type": "HOLDING_CONCENTRATION", "ticker": "ONE", "severity": "HIGH",
             "portfolio_weight": 0.60, "evidence_text": "One represents 60% of invested cost.", "citation": "Policy"},
            {"flag_type": "HOLDING_CONCENTRATION", "ticker": "TWO", "severity": "MEDIUM",
             "portfolio_weight": 0.30, "evidence_text": "Two represents 30% of invested cost.", "citation": "Policy"},
        ]
        notes = {"notes": [
            {"id": "R1", "explanation": "Review how an issuer-specific setback could affect your portfolio."},
            {"id": "R2", "explanation": "Sell this position to reach an exposure of 10%."},
            {"id": "R3", "explanation": "This explanation has no corresponding source."},
        ]}
        result = SimpleNamespace(generated_via="LLM", text=json.dumps(notes))
        with (
            patch.object(recommender, "settings", SimpleNamespace(groq_api_key="fixture")),
            patch.object(recommender.LLMService, "get_instance") as mock_llm,
        ):
            mock_llm.return_value.generate.return_value = result
            report = recommender.generate_recommendations({"risk_flags": flags})
        sent = json.loads(mock_llm.return_value.generate.call_args.kwargs["prompt"])
        self.assertEqual(sent, [{"id": "R1", "risk_type": "HOLDING_CONCENTRATION"},
                                {"id": "R2", "risk_type": "HOLDING_CONCENTRATION"}])
        first, second = report["recommendations"]
        self.assertEqual(first["nextCheck"], notes["notes"][0]["explanation"])
        self.assertEqual(second["priority"], "MEDIUM")
        self.assertIn("company-specific setback", second["nextCheck"])


class PublicContextTests(unittest.IsolatedAsyncioTestCase):
    def test_news_discards_old_stories_and_spreads_coverage(self):
        def story(title, url, published, source="Publisher"):
            return {"title": title, "url": url, "published_at": published, "source": source}

        recent = "Fri, 20 Nov 2026 12:00:00 GMT"
        batches = {
            "ONE": [
                story("One earnings beat expectations", "https://example.com/one", recent),
                story("One earnings beat expectations - Press", "https://example.com/duplicate", recent, "Press"),
                story("Old story", "https://example.com/old", "2026-10-01T00:00:00Z"),
                story("One appoints new director", "https://example.com/director", recent),
            ],
            "TWO": [story("Two releases its quarterly results", "https://example.com/two", recent)],
            "MARKET": [story("Nifty ends higher", "https://example.com/nifty", recent)],
        }
        rows = select_report_news(batches, datetime(2026, 11, 22, tzinfo=timezone.utc))
        self.assertEqual([row["ticker"] for row in rows], ["ONE", "TWO", "MARKET", "ONE"])
        self.assertTrue(all(row["publishedAt"] == "2026-11-20T12:00:00+00:00" for row in rows))
        self.assertNotIn("https://example.com/duplicate", [row["url"] for row in rows])

    async def test_index_snapshot_uses_the_exchange_timestamp(self):
        payload = {"nseTimestamp": "20-Nov-2026 15:30:00", "updatedAt": "2026-11-22T16:00:00Z",
                   "index": {"indexName": "NIFTY 50", "last": 25800.6, "percChange": 1.12}}
        with patch.object(nse_market, "_tool", AsyncMock(return_value=payload)) as transport:
            index = await nse_market.NseMcpProvider().index_snapshot()
        transport.assert_awaited_once_with(nse_market.LIVE, "cm_get_index_quote", {"indexName": "NIFTY 50"})
        self.assertEqual(index["timestamp"], "2026-11-20T15:30:00+05:30")
        self.assertEqual(index["dayChangePercent"], 1.12)
