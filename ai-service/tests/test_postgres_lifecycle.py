"""Real Postgres checks. Run only against a disposable migrated test project."""

import asyncio
import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.services.cache_service import cache_service


@unittest.skipUnless(os.environ.get("SUPABASE_TEST_DB_URL"), "Test database not configured")
class PostgresLifecycleTests(unittest.TestCase):
    def test_report_stream_and_cache_survive_application_restart(self):
        from src.api import main
        from src.middleware import internal_api_key

        settings = replace(main.settings, supabase_db_url=os.environ["SUPABASE_TEST_DB_URL"], internal_api_key="fixture-key")
        params = {
            "user_id": "test-postgres-report",
            "include_news": False,
            "portfolio": [
                {
                    "ticker": "FIXTURE", "name": "Fixture bond", "quantity": 2, "avg_buy_price": 100,
                    "asset_type": "BOND", "invested_cost": 200, "price_source": None, "price_as_of": None,
                }
            ],
        }

        from src.core.nodes import recommender
        with patch.object(main, "settings", settings), patch.object(internal_api_key, "settings", settings):
            with patch.object(recommender, "settings", replace(settings, groq_api_key="")):
                with TestClient(main.app, backend_options={"loop_factory": asyncio.SelectorEventLoop}) as client:
                    async def seed():
                        await cache_service.set("phase-three-integration", {"market": "fixture"}, 300)
                    client.portal.call(seed)
                    response = client.post("/generate-report", json=params, headers={"X-Internal-Key": "fixture-key"})
                    self.assertEqual(response.status_code, 200)
                    events = response.text.split("\n\n")
                    complete = next((e for e in events if e.startswith("event: complete")), None)
                    self.assertIsNotNone(complete, response.text)
                    result = json.loads(complete.split("data: ", 1)[1])["report_json"]
                    self.assertEqual(result["portfolioSummary"]["investedCost"], 200)
                    self.assertIsNone(result["portfolioSummary"]["marketValue"])

                    qa_response = client.post("/qa", json={
                        "user_id": params["user_id"],
                        "question": "What is my portfolio worth?",
                        "portfolio_context": [],
                    }, headers={"X-Internal-Key": "fixture-key"})
                    self.assertEqual(qa_response.status_code, 200)
                    self.assertIn('"node": "retrieve_portfolio"', qa_response.text)
                    self.assertIn('"answerStatus": "unavailable"', qa_response.text)
                    self.assertIn("No confirmed holdings", qa_response.text)

                with TestClient(main.app, backend_options={"loop_factory": asyncio.SelectorEventLoop}) as client:
                    cached = client.portal.call(cache_service.get, "phase-three-integration")
                    self.assertEqual(cached["market"], "fixture")
