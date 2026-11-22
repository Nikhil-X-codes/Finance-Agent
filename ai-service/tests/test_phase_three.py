"""Statement-format and shared concentration checks using synthetic inputs."""

import asyncio
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from groq import RateLimitError
import httpx
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
import xlwt

from src.api.routes.portfolio import PortfolioRiskRequest, get_portfolio_risk_status
from src.config.models import Holding
from src.services.portfolio_facts import summarize_portfolio
from src.core.nodes.risk_analyzer import analyze_portfolio_risk
from src.services.trade_review import review_trade
from src.core.graph import create_report_graph
from src.services.market_data import market_data
from src.services.pdf_service import PDFService
from src.services.spreadsheet_service import SpreadsheetService
from src.services.statement_extraction import StatementExtraction, parse_sections, validate_extractions


class StatementFixtures(unittest.TestCase):
    def test_standard_spreadsheet_does_not_require_groq(self):
        with TemporaryDirectory() as directory:
            workbook = Workbook()
            sheet = workbook.active
            sheet.append([None, "Holdings Statement"])
            sheet.append([None, "Holdings as on", "2026-11-20"])
            sheet.append(["Trading Symbol", "ISIN", "Qty", "Avg. Buy Price", "LTP", "Unrealised P&L %"])
            sheet.append(["TCS", "INE467B01029", 2, 2500, 2700, 8])
            sheet.append(["TCS", "INE467B01029", 3, 2530, None])
            sheet.append(["INFY", None, 9, None, None])
            path = Path(directory) / "holdings.xlsx"
            workbook.save(path)
            workbook.close()
            with patch("src.services.spreadsheet_service.parse_sections") as parse:
                result = SpreadsheetService().parse_statement(str(path))
            parse.assert_not_called()
        self.assertEqual(result.coverage_end.isoformat(), "2026-11-20")
        self.assertEqual([(row.ticker, row.quantity) for row in result.holdings], [("TCS", 2), ("TCS", 3)])
        self.assertEqual(result.holdings[0].isin, "INE467B01029")
        self.assertEqual(result.holdings[0].current_price, 2700)
        self.assertIsNone(result.holdings[1].current_price)
        self.assertEqual(len(result.unrecognized_rows), 1)

    def test_rate_limited_batch_retries_without_reprocessing_prior_batches(self):
        request = httpx.Request("POST", "https://example.test")
        limited = RateLimitError(
            "rate limit", response=httpx.Response(429, headers={"Retry-After": "2"}, request=request), body=None,
        )
        response = SimpleNamespace(
            content='{"holdings":[{"ticker":"TCS","quantity":2,"avg_buy_price":100}]}',
            response_metadata={"finish_reason": "stop"},
        )
        with (
            patch("src.services.statement_extraction.settings", SimpleNamespace(groq_api_key="fixture", groq_model="fixture")),
            patch("src.services.statement_extraction.ChatGroq") as chat,
            patch("src.services.statement_extraction.sleep") as wait,
        ):
            invoke = chat.return_value.bind.return_value.invoke
            invoke.side_effect = [response, limited, response]
            parsed = parse_sections(["first batch", "second batch"])
        self.assertEqual(len(parsed.holdings), 2)
        self.assertEqual([call.args[0][-1][1] for call in invoke.call_args_list], [
            "first batch", "second batch", "second batch",
        ])
        wait.assert_called_once_with(2)

    def test_json_extraction_validates_rows_and_rejects_truncated_output(self):
        response = SimpleNamespace(
            content='{"holdings":[{"ticker":"TCS","quantity":2,"avg_buy_price":100}]}',
            response_metadata={"finish_reason": "stop"},
        )
        with (
            patch("src.services.statement_extraction.settings", SimpleNamespace(groq_api_key="fixture", groq_model="fixture")),
            patch("src.services.statement_extraction.ChatGroq") as chat,
        ):
            chat.return_value.bind.return_value.invoke.return_value = response
            parsed = parse_sections(["Ticker,Quantity,Average Buy Price\nTCS,2,100"])
            chat.return_value.bind.assert_called_once_with(response_format={"type": "json_object"})
            self.assertEqual(parsed.holdings[0].quantity, 2)
            self.assertIsNone(parsed.holdings[0].current_price)

            response.response_metadata["finish_reason"] = "length"
            with self.assertRaisesRegex(RuntimeError, "output limit"):
                parse_sections(["Statement rows"])

            response.response_metadata["finish_reason"] = "stop"
            response.content = '{"holdings":['
            with self.assertRaisesRegex(RuntimeError, "invalid JSON data"):
                parse_sections(["Statement rows"])

            invoke = chat.return_value.bind.return_value.invoke
            invoke.reset_mock()
            invoke.side_effect = [response, SimpleNamespace(
                content='{"holdings":[{"ticker":"TCS","quantity":2,"avg_buy_price":100}]}',
                response_metadata={"finish_reason": "stop"},
            )]
            parsed = parse_sections(["Statement rows"])
            self.assertEqual(len(parsed.holdings), 1)
            self.assertEqual(invoke.call_count, 2)
            self.assertIn("compact JSON", invoke.call_args.args[0][0][1])

    def test_all_supported_formats_extract_rows(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            csv = folder / "fixture.csv"
            csv.write_text("As of,2025-04-01\nTicker,Quantity\n" + "INFY,2\n" * 101 + "TCS,4\n", encoding="utf-8")
            xlsx = folder / "fixture.xlsx"
            book = Workbook()
            book.active.append(["As of", "2025-04-01"])
            book.active.append(["TCS", 4])
            book.save(xlsx)
            book.close()
            xls = folder / "fixture.xls"
            legacy = xlwt.Workbook()
            sheet = legacy.add_sheet("Holdings")
            sheet.write(0, 0, "TCS")
            sheet.write(0, 1, 4)
            legacy.save(str(xls))

            pdf = folder / "fixture.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=300, height=200)
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
            })
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 30 100 Td (TCS 4) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
            writer.write(pdf)
            writer.close()

            for path in (csv, xlsx, xls):
                with self.subTest(path=path.suffix):
                    with patch("src.services.spreadsheet_service.parse_sections") as parse:
                        SpreadsheetService().parse_statement(str(path))
                    sections = parse.call_args.args[0]
                    self.assertIn("TCS,4", "\n".join(sections))
                    if path == csv:
                        self.assertEqual(len(sections), 7)
                        self.assertIn("TCS,4", sections[-1])

            with patch("src.services.pdf_service.parse_sections") as parse:
                PDFService().parse_statement(str(pdf))
            self.assertIn("TCS 4", parse.call_args.args[0][0])

    def test_bad_rows_are_reported_without_filling_missing_prices(self):
        parsed = validate_extractions([StatementExtraction(
            coverage_end="2025-04-01",
            holdings=[
                {"ticker": "TCS", "quantity": 4, "avg_buy_price": 100},
                {"ticker": "BAD", "quantity": 2},
            ],
            realized_trades=[
                {"ticker": "TCS", "quantity": 2, "buy_price": 100, "sell_date": "2025-04-01", "realized_pnl": 25},
            ],
        )])
        self.assertEqual(len(parsed.holdings), 1)
        self.assertIsNone(parsed.holdings[0].current_price)
        self.assertIsNone(parsed.holdings[0].isin)
        self.assertIsNone(parsed.realized_trades[0].sell_price)
        self.assertEqual(parsed.coverage_end.isoformat(), "2025-04-01")
        self.assertEqual(len(parsed.unrecognized_rows), 1)


class SharedRiskTests(unittest.TestCase):
    def test_report_keeps_public_quotes_separate_from_statement_accounting(self):
        holding = Holding(
            ticker="tcs", name="TCS", quantity=2, avg_buy_price=100, current_price=110,
            invested_cost=200, market_value=220, sector="IT",
        )
        provider = SimpleNamespace(quote=AsyncMock(return_value={
            "current_price": 125, "timestamp": "2025-04-02T12:00:00+05:30",
            "source": "Fixture feed", "status": "last_published",
        }))
        with (
            patch.object(market_data, "provider", provider),
            patch("src.core.nodes.recommender.settings", SimpleNamespace(groq_api_key="")),
        ):
            report = asyncio.run(create_report_graph().ainvoke({
                "raw_holdings": [holding], "include_news": False,
            }))["report_json"]
        provider.quote.assert_awaited_once_with("TCS")
        self.assertEqual(report["portfolioSummary"]["marketValue"], 220)
        self.assertEqual(report["portfolioSummary"]["unrealizedPnl"], 20)
        self.assertIn("INR 125.00 | 2025-04-02T12:00:00+05:30 | Fixture feed | last published", report["markdown"])

    def test_report_and_dashboard_have_identical_concentration_policy(self):
        in_scope = Holding(ticker="TCS", name="TCS", quantity=4, avg_buy_price=100, sector="IT")
        closed = Holding(ticker="INFY", name="Infosys", quantity=80, avg_buy_price=100, status="REALIZED")
        holdings = [in_scope, closed]
        dashboard = asyncio.run(get_portfolio_risk_status(PortfolioRiskRequest(portfolio=holdings)))
        report = analyze_portfolio_risk({"normalized_holdings": holdings})
        self.assertEqual(dashboard["overall_risk"], report["overall_risk"])
        self.assertEqual(dashboard["overall_risk"], "HIGH")
        self.assertEqual(dashboard["flags"][0]["portfolio_weight"], 1)

    def test_context_keeps_unknown_prices_and_totals_unavailable(self):
        holdings = [{"ticker": "TCS", "quantity": 2, "avg_buy_price": 100, "current_price": None}]
        result = summarize_portfolio(holdings)
        self.assertEqual(result["total_invested"], 200)
        self.assertIsNone(result["total_current"])
        self.assertIsNone(result["unrealized_pnl"])

    def test_trade_review_stays_unavailable_when_the_model_fails(self):
        state = {
            "raw_holdings": [
                {"ticker": "TCS", "quantity": 4, "avg_buy_price": 100},
                {"ticker": "INFY", "quantity": 4, "avg_buy_price": 100},
            ],
            "proposed_trade": {"ticker": "TCS", "action": "SELL", "quantity": 3, "price": 200},
        }
        with patch("src.services.trade_review.get_llm", side_effect=RuntimeError("provider offline")):
            result = asyncio.run(review_trade(state["proposed_trade"], state["raw_holdings"]))
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["allowed"])
        self.assertEqual(result["new_portfolio_weight"], 20)
