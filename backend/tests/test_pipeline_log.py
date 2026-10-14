import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.parse_api import app
from app.integrations.models.tg_models import JobVacancy


class PipelineLogTests(unittest.TestCase):
    def test_messages_llm_responses_skips_database_and_final_results_are_logged(self):
        with TemporaryDirectory() as directory:
            log_path = Path(directory) / "pipeline.log"
            backend = SimpleNamespace(
                name="tg_parser", open=AsyncMock(), close=AsyncMock(),
                fetch=AsyncMock(side_effect=[[
                    SimpleNamespace(id=1, date=datetime.now(timezone.utc), text="Вакансия Python"),
                    SimpleNamespace(id=2, date=datetime.now(timezone.utc), text="Привет всем"),
                    SimpleNamespace(id=3, date=datetime.now(timezone.utc), text="Вакансия invalid"),
                ], RuntimeError("channel test failure")]),
            )
            record = JobVacancy(title="Python", raw_text="Вакансия Python", technologies=["Python"])
            llm = SimpleNamespace(model="test-model", complete=AsyncMock(
                side_effect=[record.model_dump_json(), "invalid-json-response"],
            ))
            with patch.dict(os.environ, {
                "PARSE_LOG_PATH": str(log_path),
                "VACANCIES_DB_PATH": str(Path(directory) / "vacancies.duckdb"),
            }), patch("app.integrations.sources.build_backend", return_value=backend), \
                    patch("app.integrations.sources.LLMClient", return_value=llm), TestClient(app) as client:
                response = client.post("/api/v1/parse", json={"chats": ["jobs", "broken"]})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["count"], 1)
                self.assertEqual(len(response.json()["errors"]), 2)
                self.assertEqual(client.get("/api/v1/vacancies/export.xlsx").status_code, 200)
            logs = log_path.read_text(encoding="utf-8")
            for event in (
                "parse.start", "telegram.connect", "channel.fetch.done", "message.received",
                "message.skipped", "llm.request", "llm.response", "llm.invalid_response",
                "vacancy.parsed", "channel.fetch.failed", "search.done", "telegram.disconnect",
                "db.save.done", "parse.done", "db.read.done", "xlsx.build.done", "export.done",
            ):
                self.assertIn(event, logs)
            self.assertIn("Привет всем", logs)
            self.assertIn("invalid-json-response", logs)
            self.assertIn("no_keywords", logs)
            self.assertIn("channel test failure", logs)
            entries = [json.loads(line.split(" ", 4)[4]) for line in logs.splitlines()
                       if " parse.start " in line or " parse.done " in line or " db.save.done " in line]
            self.assertEqual(len({entry["run_id"] for entry in entries}), 1)
            self.assertNotEqual(entries[0]["run_id"], "-")


if __name__ == "__main__":
    unittest.main()
