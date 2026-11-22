"""Regression checks for the private API and concurrent Q&A retrieval."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from langsmith import get_tracing_context, tracing_context

from src.core.qa_graph import create_qa_graph
from src.core.qa_types import GroundedAnswer, ParsedQuestion, QAProviders
from src.middleware import internal_api_key


class ApiBoundaryTests(unittest.TestCase):
    def test_api_home_points_to_frontend_and_private_routes_stay_protected(self):
        from src.api.main import app

        client = TestClient(app)
        with patch.object(internal_api_key, "settings", SimpleNamespace(internal_api_key="service-key")):
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn('href="http://localhost:3000"', response.text)
            self.assertEqual(client.get("/favicon.ico").status_code, 204)
            self.assertEqual(client.get("/docs").status_code, 403)
            self.assertEqual(client.get("/openapi.json").status_code, 403)
            self.assertEqual(client.post("/qa").status_code, 403)

    def setUp(self):
        app = FastAPI()
        app.add_middleware(internal_api_key.InternalApiKeyMiddleware)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.post("/qa")
        async def qa():
            async def stream():
                yield json.dumps({"tracing": get_tracing_context()["enabled"]})

            return StreamingResponse(stream())

        self.client = TestClient(app)

    def test_direct_access_requires_service_key(self):
        with patch.object(internal_api_key, "settings", SimpleNamespace(internal_api_key="service-key")):
            self.assertEqual(self.client.get("/health").status_code, 200)
            for path in ("/qa", "/parse-statement", "/generate-report", "/validate-trade", "/v1/stocks/popular"):
                with self.subTest(path=path):
                    self.assertEqual(self.client.post(path).status_code, 403)
            self.assertEqual(self.client.post("/qa", headers={"X-Internal-Key": "incorrect"}).status_code, 403)

    def test_missing_service_configuration_fails_closed(self):
        with patch.object(internal_api_key, "settings", SimpleNamespace(internal_api_key="")):
            self.assertEqual(self.client.get("/health").status_code, 200)
            self.assertEqual(self.client.post("/qa").status_code, 503)

    def test_authorized_sse_suppresses_inherited_tracing(self):
        with patch.object(internal_api_key, "settings", SimpleNamespace(internal_api_key="service-key")):
            with tracing_context(enabled=True):
                response = self.client.post("/qa", headers={"X-Internal-Key": "service-key"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tracing": False})


class PortfolioIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_overlapping_questions_use_their_own_records(self):
        ready = asyncio.Event()
        waiting = 0

        async def classify(*_):
            return ParsedQuestion(intent="clarify")

        async def answer(query, evidence):
            nonlocal waiting
            waiting += 1
            if waiting == 2:
                ready.set()
            await ready.wait()
            return GroundedAnswer(text=query.symbols[0], evidence_ids=[item["id"] for item in evidence])

        async def market(*_):
            self.fail("Portfolio questions must not call a market provider")

        def state(symbol):
            return {
                "question": f"What do I hold in {symbol}?",
                "raw_holdings": [{
                    "ticker": symbol, "quantity": 2, "avg_buy_price": 10, "status": "UNREALIZED",
                }],
            }

        graph = create_qa_graph()
        context = QAProviders(classify, answer, market)
        first, second = await asyncio.wait_for(asyncio.gather(
            graph.ainvoke(state("ALPHA"), context=context),
            graph.ainvoke(state("BETA"), context=context),
        ), timeout=5)

        for answer, own, other in ((first, "ALPHA", "BETA"), (second, "BETA", "ALPHA")):
            self.assertEqual(answer["question_type"], "portfolio")
            citations = json.dumps(answer["qa_citations"])
            self.assertIn(own, citations)
            self.assertNotIn(other, citations)


if __name__ == "__main__":
    unittest.main()
