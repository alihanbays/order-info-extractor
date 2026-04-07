"""Integration tests for the end-to-end fixture pipeline."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from order_info_extractor.config import AppConfig, OpenAIConfig, PathsConfig, SourceConfig
from order_info_extractor.factory import create_pipeline


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="order-info-test-"))
        self.config = AppConfig(
            source=SourceConfig(
                provider="fixture",
                fixture_path="tests/fixtures/mock_outlook_inbox.json",
                fixture_llm_path="tests/fixtures/mock_llm_responses.json",
            ),
            openai=OpenAIConfig(api_key=""),
            paths=PathsConfig(output_root=str(self.temp_dir)),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fixture_pipeline_creates_export_review_and_skip_records(self) -> None:
        pipeline = create_pipeline(self.config)
        summary = pipeline.run(limit=10)

        self.assertEqual(summary.approved_count, 2)
        self.assertEqual(summary.review_count, 1)
        self.assertEqual(summary.skipped_count, 1)
        self.assertTrue(Path(summary.export_path).exists())
        self.assertTrue(Path(summary.manifest_path).exists())

        review_file = self.temp_dir / "manual_review" / "msg-1003.json"
        self.assertTrue(review_file.exists())

        export_contents = Path(summary.export_path).read_text()
        self.assertIn("D\t3\tCASE\t24.0", export_contents)
        self.assertIn("D\t54\tCASE\t110.0", export_contents)

    def test_second_run_is_fully_idempotent(self) -> None:
        pipeline = create_pipeline(self.config)
        first_run = pipeline.run(limit=10)
        second_run = pipeline.run(limit=10)

        self.assertEqual(first_run.approved_count, 2)
        self.assertEqual(second_run.approved_count, 0)
        self.assertEqual(second_run.review_count, 0)
        self.assertEqual(second_run.skipped_count, 4)


if __name__ == "__main__":
    unittest.main()
