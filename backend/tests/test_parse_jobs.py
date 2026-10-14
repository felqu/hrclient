import json
import os
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.integrations.models.tg_models import JobVacancy
from app.services.parse_jobs import ParseJobManager, ParseSettings
from app.services.vacancy_store import VacancyStore
from app.services.vacancy_view import filter_vacancies


class ParseJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = VacancyStore(Path(self.temp.name) / "vacancies.duckdb")
        self.manager = ParseJobManager(self.store)
        env = patch.dict(os.environ, {"PARSE_LOG_PATH": str(Path(self.temp.name) / "pipeline.log")})
        env.start()
        self.addCleanup(env.stop)
        self.settings = ParseSettings(["jobs"], date(2026, 10, 1), date(2026, 10, 31))

    def backend(self, messages):
        return SimpleNamespace(name="tg_parser", open=AsyncMock(), close=AsyncMock(),
                               fetch=AsyncMock(return_value=messages))

    def message(self, message_id, text="Вакансия Python"):
        return SimpleNamespace(id=message_id, text=text, date=datetime(2026, 10, 14, tzinfo=timezone.utc))

    def wait(self, job_id):
        self.assertTrue(self.manager.jobs[job_id].finished.wait(timeout=5), "Background job did not finish")
        return self.manager.snapshot(job_id)

    def test_live_progress_does_not_wait_for_llm_and_results_persist(self):
        entered, release = Event(), Event()

        async def complete(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return JobVacancy(title="Python", raw_text="Вакансия Python").model_dump_json()

        llm = SimpleNamespace(model="test-model", complete=complete, aclose=AsyncMock())
        with patch("app.integrations.sources.build_backend", return_value=self.backend([
            self.message(1), self.message(2, "Привет всем"),
        ])), patch("app.integrations.sources.LLMClient", return_value=llm):
            job_id = self.manager.start(self.settings)
            try:
                self.assertTrue(entered.wait(3))
                snapshot = self.manager.snapshot(job_id)
                self.assertFalse(snapshot["terminal"])
                self.assertEqual(snapshot["received"], 2)
                self.assertEqual(snapshot["processed"], 0)
                self.assertEqual(snapshot["llm_requests"], 1)
                self.assertIn("LLM", snapshot["stage"])
                with self.assertRaisesRegex(ValueError, "уже идёт"):
                    self.manager.start(self.settings)
            finally:
                release.set()
            snapshot = self.wait(job_id)
        self.assertEqual(snapshot["state"], "completed")
        self.assertEqual(snapshot["progress"], 1)
        self.assertEqual(snapshot["processed"], 2)
        self.assertEqual(snapshot["skipped"], 1)
        self.assertEqual(snapshot["found"], 1)
        self.assertEqual(snapshot["saved"], 1)
        self.assertEqual(len(self.store.list()), 1)
        llm.aclose.assert_awaited_once()

    def test_llm_errors_are_visible_in_progress_and_final_summary(self):
        llm = SimpleNamespace(model="test-model", complete=AsyncMock(return_value="invalid-json"),
                              aclose=AsyncMock())
        with patch("app.integrations.sources.build_backend", return_value=self.backend([self.message(1)])), \
                patch("app.integrations.sources.LLMClient", return_value=llm):
            snapshot = self.wait(self.manager.start(self.settings))
        self.assertEqual(snapshot["state"], "completed_with_errors")
        self.assertEqual(snapshot["llm_errors"], 1)
        self.assertEqual(snapshot["processed"], 1)
        self.assertEqual(snapshot["saved"], 0)
        self.assertEqual(len(snapshot["errors"]), 1)

    def test_cancel_preserves_accepted_vacancies_and_does_not_process_next_message(self):
        entered, release = Event(), Event()

        async def complete(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return JobVacancy(title="Python", raw_text="Вакансия Python").model_dump_json()

        llm = SimpleNamespace(model="test-model", complete=complete, aclose=AsyncMock())
        with patch("app.integrations.sources.build_backend", return_value=self.backend([
            self.message(1), self.message(2),
        ])), patch("app.integrations.sources.LLMClient", return_value=llm):
            job_id = self.manager.start(self.settings)
            try:
                self.assertTrue(entered.wait(3))
                self.manager.stop(job_id)
                self.assertEqual(self.manager.snapshot(job_id)["state"], "stopping")
            finally:
                release.set()
            snapshot = self.wait(job_id)
        self.assertEqual(snapshot["state"], "cancelled")
        self.assertEqual(snapshot["processed"], 1)
        self.assertEqual(snapshot["saved"], 1)
        self.assertEqual(snapshot["llm_requests"], 1)
        self.assertEqual(len(self.store.list()), 1)

    def test_invalid_settings_do_not_start_a_job(self):
        for settings in (ParseSettings([], date.today(), date.today()),
                         ParseSettings(["jobs"], date(2026, 10, 15), date(2026, 10, 14))):
            with self.assertRaises(ValueError):
                self.manager.start(settings)
        self.assertEqual(self.manager.history(), [])

    def test_configuration_failure_is_a_failed_job_not_empty_success(self):
        with patch("app.services.parse_jobs.TelegramGateway", side_effect=ValueError("Bad LLM config")):
            snapshot = self.wait(self.manager.start(self.settings))
        self.assertEqual(snapshot["state"], "failed")
        self.assertIn("Bad LLM config", snapshot["errors"])


class VacancyFilterTests(unittest.TestCase):
    def test_text_and_date_filters_preserve_original_vacancies(self):
        records = [JobVacancy(title="Python", raw_text="Вакансия", published_date=date(2026, 10, 14)),
                   JobVacancy(title="Java", raw_text="Вакансия", published_date=date(2026, 10, 1)),
                   JobVacancy(title="Analyst", raw_text="SQL Python", published_date=None)]
        self.assertEqual(len(filter_vacancies(records, text="python")), 2)
        self.assertEqual(filter_vacancies(records, date_from=date(2026, 10, 10), include_undated=False),
                         [records[0]])
        self.assertEqual(len(records), 3)


if __name__ == "__main__":
    unittest.main()
