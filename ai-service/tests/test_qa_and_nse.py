"""QA fixtures and provider-adapter regression tests."""

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from evals.run import check_case, load_fixture, run_case, threshold_failures
from src.api.routes import stocks
from src.api.routes import mf_comparison
from src.api.routes.stocks import _quote_fields
from src.core.qa_graph import create_qa_graph, market_with_provider
from src.core.qa_types import QAProviders
from src.core.tools import nse_market
from src.core.tools.mf_tools import MFTools
from src.services.market_data import market_data


class QuestionRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_market_analytics_never_substitute_a_quote(self):
        graph = create_qa_graph()
        providers = QAProviders(AsyncMock(), AsyncMock(), AsyncMock())
        for question in (
            "Show INFY's closing prices for the last 30 trading sessions.",
            "Compare INFY's current quote with its 50-day moving average.",
            "Show corporate actions for INFY.",
            "List corporate actions for infy.",
        ):
            with self.subTest(question=question):
                state = await graph.ainvoke({"question": question}, context=providers)
                self.assertEqual(state["answer_status"], "unavailable")
                self.assertIn("unavailable in chat", state["qa_response"])
        providers.market.assert_not_awaited()
        providers.answer.assert_not_awaited()

    def test_eval_gates_fail_on_missing_or_low_scores(self):
        policy = {"fixture_version": 1, "minimums": {"all": {"faithfulness": 0.8, "context_recall": 0.8}}}
        failures = threshold_failures({"all": {"faithfulness": 0.7}}, policy, 1)
        self.assertEqual([entry["actual"] for entry in failures], [0.7, None])
        self.assertEqual(threshold_failures({"all": {"faithfulness": 0.8, "context_recall": 1}}, policy, 1), [])

    async def test_versioned_question_fixture(self):
        fixture = load_fixture()
        graph = create_qa_graph()
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                result = await run_case(graph, fixture, case)
                self.assertEqual(check_case(case, result), [])


class MutualFundComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_fund_comparison_uses_mfapi_category_and_dated_nav(self):
        async def respond(request):
            self.assertEqual(request.url.host, "api.mfapi.in")
            self.assertNotIn("X-API-Key", request.headers)
            if request.url.path == "/mf":
                return httpx.Response(200, json=[
                    {"schemeCode": 1001, "schemeName": "Example Large Cap Fund"},
                    {"schemeCode": 1002, "schemeName": "Example Focused Large Cap Fund"},
                ])
            code = int(request.url.path.split("/")[2])
            self.assertEqual(request.url.path, f"/mf/{code}/latest")
            category = "Large Cap Fund" if code == 1001 else "Large & Mid Cap Fund"
            return httpx.Response(200, json={
                "meta": {
                    "scheme_code": code, "scheme_name": "Example fund",
                    "scheme_category": f"Equity Scheme - {category}", "fund_house": "Example AMC",
                },
                "data": [{"nav": "123.456", "date": "20-11-2026"}],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            rows = await mf_comparison._fetch_comparison(client, "Large Cap")

        self.assertEqual([fund["schemeCode"] for fund in rows], [1001])
        self.assertEqual(rows[0]["nav"], 123.456)
        self.assertEqual(rows[0]["navDate"], "2026-11-20")
        self.assertIsNone(rows[0]["cagr"]["1Y"])

    async def test_sectoral_funds_use_scheme_category_and_deduplicate_catalog_matches(self):
        catalog_row = {"schemeCode": 101, "schemeName": "Example Technology Fund"}

        async def respond(request):
            if request.url.path == "/mf":
                return httpx.Response(200, json=[catalog_row, catalog_row])
            return httpx.Response(200, json={
                "meta": {
                    "scheme_code": 101, "scheme_name": "Fund", "fund_house": "Example AMC",
                    "scheme_category": "Equity Scheme - Sectoral/ Thematic",
                },
                "data": [{"nav": "97.25", "date": "20-11-2026"}],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            rows = await mf_comparison._fetch_comparison(client, "Sectoral/Thematic")

        self.assertEqual([fund["schemeCode"] for fund in rows], [101])

    async def test_report_metadata_resolves_isin_using_the_same_provider(self):
        async def respond(request):
            if request.url.path == "/mf":
                return httpx.Response(200, json=[{"schemeCode": 101, "isinGrowth": "INF000000001"}])
            self.assertEqual(request.url.path, "/mf/101/latest")
            return httpx.Response(200, json={
                "meta": {"scheme_code": 101, "scheme_category": "Equity Scheme - Mid Cap Fund"},
                "data": [],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await MFTools(client).get_metadata("INF000000001")

        self.assertEqual(result.data["category"], "Equity Scheme - Mid Cap Fund")
        self.assertEqual(result.data["source"], "MFapi.in")

    async def test_fund_comparison_reports_source_without_inventing_a_common_date(self):
        rows = [{"schemeCode": 101, "navDate": "2026-11-20"}]
        with patch.object(
            mf_comparison.cache_service, "get_or_fetch", AsyncMock(return_value=SimpleNamespace(value=rows)),
        ) as cache:
            result = await mf_comparison.get_mf_comparison("Large Cap", refresh=False)
        self.assertEqual(cache.await_args.args[0], "MFAPI_COMPARISON:Large Cap")
        self.assertEqual(result["source"], "MFapi.in")
        self.assertEqual(result["funds"], rows)
        self.assertIsNone(result["dataAsOf"])


class NseMarketTests(unittest.IsolatedAsyncioTestCase):
    async def test_market_movers_uses_provider_symbols_and_quote_timestamps(self):
        ranking = {"gainers": [{"symbol": "OAL"}, {"symbol": "OAL"}], "losers": [{"symbol": "BALAXI"}]}
        quote = {"timestamp": "2025-04-02T15:30:00+05:30", "current_price": 150, "source": "NSE CM Market Live"}
        with (
            patch.object(market_data, "provider", nse_market.NseMcpProvider()),
            patch.object(nse_market, "_tool", AsyncMock(return_value=ranking)) as transport,
            patch.object(nse_market, "get_nse_quote", AsyncMock(return_value=quote)),
        ):
            result = await stocks.get_popular_stocks()
        transport.assert_awaited_once_with(nse_market.LIVE, "nse_get_market_movers", {"indexName": "", "limit": 5})
        self.assertEqual([(row["symbol"], row["moverType"]) for row in result["stocks"]], [
            ("OAL", "gainers"), ("BALAXI", "losers"),
        ])
        self.assertEqual(result["stocks"][0]["marketTimestamp"], quote["timestamp"])

    async def test_disabled_market_never_calls_either_nse_server(self):
        with (
            patch.object(market_data, "provider", None),
            patch.object(nse_market, "_tool", AsyncMock()) as transport,
        ):
            self.assertEqual((await stocks.get_popular_stocks())["status"], "disabled")
            self.assertEqual((await stocks.search_stocks("INFY"))["status"], "disabled")
            self.assertEqual((await market_with_provider("INFY", None))["status"], "disabled")
            self.assertEqual(await market_with_provider("INFY", date(2025, 4, 2)), {})
            transport.assert_not_awaited()

    async def test_search_uses_bhavcopy_for_matches_and_live_server_for_quote(self):
        lookup = {"results": [{"symbol": "TCS", "last_close": 100}]}
        live_quote = {"current_price": 125, "source": "NSE CM Market Live", "status": "delayed"}
        with (
            patch.object(market_data, "provider", nse_market.NseMcpProvider()),
            patch.object(nse_market, "_tool", AsyncMock(return_value=lookup)) as transport,
            patch.object(nse_market, "get_nse_quote", AsyncMock(return_value=live_quote)) as live,
            patch.object(stocks.stock_tools, "get_fundamentals", AsyncMock(return_value=SimpleNamespace(data={}))),
        ):
            reply = await stocks.search_stocks("TATA CONSULTANCY")
            transport.assert_awaited_once_with(nse_market.BHAVCOPY, "search_symbols", {"query": "TATA CONSULTANCY"})
            live.assert_awaited_once_with("TCS")
        self.assertEqual(reply["results"][0]["price"], 125)
        self.assertEqual(reply["results"][0]["source"], "NSE CM Market Live")

    async def test_provider_can_be_swapped_for_stocks_and_qa(self):
        provider = SimpleNamespace(
            quote=AsyncMock(return_value={"source": "Fixture feed", "current_price": 150}),
            history=AsyncMock(return_value={"status": "available", "source": "Fixture feed"}),
            historical_close=AsyncMock(return_value={"source": "Fixture feed", "current_price": 145}),
        )
        with (
            patch.object(market_data, "provider", provider),
            patch.object(stocks.stock_tools, "get_fundamentals", AsyncMock(return_value=SimpleNamespace(data={}))),
        ):
            detail = await stocks.get_stock_detail("INFY")
            self.assertEqual(detail["source"]["price"], "Fixture feed")
            self.assertEqual(detail["history"]["source"], "Fixture feed")
            self.assertEqual((await market_with_provider("INFY", None))["current_price"], 150)
            self.assertEqual((await market_with_provider("INFY", date(2025, 4, 2)))["current_price"], 145)

    async def test_uses_trade_timestamp_instead_of_feed_refresh(self):
        payload = {
            "updatedAt": "2026-11-22T06:00:00Z",
            "stock": {"symbol": "TCS", "lastTradedPrice": 2376.2, "latestTimestamp": "2026-11-20 16:00:28"},
        }
        with patch.object(nse_market, "_tool", AsyncMock(return_value=payload)):
            quote = await nse_market.get_nse_quote("tcs")
        self.assertEqual(quote["timestamp"], "2026-11-20T16:00:28+05:30")
        self.assertEqual(quote["status"], "last_published")
        self.assertEqual(quote["source"], "NSE CM Market Live")
        public_quote = _quote_fields(quote)
        self.assertEqual(public_quote["quoteStatus"], "last_published")
        self.assertEqual(public_quote["marketTimestamp"], quote["timestamp"])
        self.assertEqual(public_quote["source"], quote["source"])

    def test_stale_fallback_and_missing_prices_have_distinct_statuses(self):
        self.assertEqual(_quote_fields({"current_price": 150, "fresh": False})["quoteStatus"], "stale_cache")
        self.assertEqual(_quote_fields({"current_price": None})["quoteStatus"], "unavailable")

    async def test_requested_holiday_does_not_return_previous_close(self):
        rows = [{"date": "2026-11-20", "close": 2376.2}]
        with patch.object(nse_market, "_history_rows", AsyncMock(return_value=rows)):
            self.assertEqual(await nse_market.NseMcpProvider().historical_close("TCS", date(2026, 11, 22)), {})

    def test_split_bonus_factors_apply_to_old_closes(self):
        rows = [{"date": "2025-01-01", "close": 600}, {"date": "2025-01-08", "close": 110}]
        actions = [
            {"exDate": "2025-01-03", "actionType": "SPLIT", "adjustmentFactor": 0.5},
            {"exDate": "2025-01-06", "actionType": "BONUS", "adjustmentFactor": 1 / 3},
        ]
        self.assertEqual(nse_market.adjusted_price_return(rows, actions), 10.0)
        self.assertIsNone(nse_market.adjusted_price_return(rows, [*actions, {
            "exDate": "2025-01-07", "actionType": "BONUS",
        }]))
