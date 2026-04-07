"""Unit tests for retry and backoff behavior."""

from __future__ import annotations

import unittest

from order_info_extractor.utils import retry_with_backoff


class RetryTests(unittest.TestCase):
    def test_retry_succeeds_after_transient_failures(self) -> None:
        attempts = {"count": 0}

        def flaky() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ValueError("transient")
            return "ok"

        result = retry_with_backoff(
            func=flaky,
            attempts=3,
            base_delay_seconds=0,
            max_delay_seconds=0,
            jitter_ratio=0,
            retryable_exceptions=(ValueError,),
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 3)


if __name__ == "__main__":
    unittest.main()
