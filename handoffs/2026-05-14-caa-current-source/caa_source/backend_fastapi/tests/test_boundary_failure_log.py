"""Tests for boundary-failure logging at every `BronzeBoundaryError` raise
site in `extraction.py` and at the catch site in `main.py`, plus
validation-error and HTTP-error handler emissions.

Plan tree: docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/
Step:      5_boundary-failure-logging
"""

from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend_fastapi.main import app

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from caa_backend.storage import BronzeStore  # noqa: E402


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages_at(self, level: int) -> list[str]:
        return [r.getMessage() for r in self.records if r.levelno == level]


class TestBoundaryFailureLog(unittest.TestCase):
    def setUp(self) -> None:
        # Step 7 of singlestore migration: `app.state.bronze_storage_dir`
        # removed (Step 6 discard); the inmemory backend handles persistence.
        os.environ["CAA_SKIP_AUTH"] = "1"
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        app.state.max_upload_bytes = 10 * 1024 * 1024
        app.state.extraction_timeout_seconds = 30
        self.client = TestClient(app)
        self.capture = _CaptureHandler()
        self.main_logger = logging.getLogger("backend_fastapi.main")
        self.extraction_logger = logging.getLogger("backend_fastapi.extraction")
        self.main_logger.addHandler(self.capture)
        self.extraction_logger.addHandler(self.capture)
        self.previous_main_level = self.main_logger.level
        self.previous_extraction_level = self.extraction_logger.level
        self.main_logger.setLevel(logging.DEBUG)
        self.extraction_logger.setLevel(logging.DEBUG)

    def tearDown(self) -> None:
        self.main_logger.removeHandler(self.capture)
        self.extraction_logger.removeHandler(self.capture)
        self.main_logger.setLevel(self.previous_main_level)
        self.extraction_logger.setLevel(self.previous_extraction_level)
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_SKIP_AUTH", None)
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def _messages_with(self, substring: str) -> list[str]:
        return [r.getMessage() for r in self.capture.records if substring in r.getMessage()]

    def test_oversized_upload_emits_boundary_failure_and_upload_failed(self) -> None:
        app.state.max_upload_bytes = 8
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("big.txt", b"this is too large", "text/plain")},
        )
        self.assertEqual(response.status_code, 413)
        boundary = [
            r for r in self.capture.records
            if r.getMessage().startswith("event=boundary_failure code=upload_too_large")
        ]
        self.assertTrue(boundary, "boundary_failure line missing for upload_too_large")
        self.assertTrue(any(r.levelno == logging.WARNING for r in boundary))
        upload_failed = [
            r for r in self.capture.records
            if r.getMessage().startswith("event=upload_failed")
            and "code=upload_too_large" in r.getMessage()
        ]
        self.assertTrue(upload_failed, "upload_failed catch-site line missing")
        self.assertTrue(any(r.levelno == logging.WARNING for r in upload_failed))
        # Failure path must NOT emit success audit.
        success_audit = [
            r for r in self.capture.records
            if r.getMessage().startswith("event=upload ")
        ]
        self.assertEqual(success_audit, [])

    def test_no_extractable_text_emits_boundary_failure(self) -> None:
        with patch(
            "backend_fastapi.extraction.extract_bronze",
            return_value={"extracted_text": "   \n\t", "metadata": {}, "tables": []},
        ):
            response = self.client.post(
                "/api/v1/uploads",
                files={"file": ("blank.txt", b"blank source", "text/plain")},
            )
        self.assertEqual(response.status_code, 422)
        warns = self._messages_with("event=boundary_failure code=no_extractable_text")
        self.assertTrue(warns)
        upload_failed = self._messages_with("event=upload_failed")
        self.assertTrue(any("code=no_extractable_text" in m for m in upload_failed))

    def test_extraction_timeout_emits_error_level_boundary_failure(self) -> None:
        def slow_extract(_: Path) -> dict:
            import time
            time.sleep(0.2)
            return {"extracted_text": "too late", "metadata": {}, "tables": []}

        app.state.extraction_timeout_seconds = 0
        with patch("backend_fastapi.extraction.extract_bronze", side_effect=slow_extract):
            response = self.client.post(
                "/api/v1/uploads",
                files={"file": ("slow.txt", b"slow text", "text/plain")},
            )
        self.assertEqual(response.status_code, 504)
        timeout_records = [
            r for r in self.capture.records
            if r.getMessage().startswith("event=boundary_failure code=extraction_timeout")
        ]
        self.assertTrue(timeout_records)
        # extraction_timeout is server-fault → ERROR level per spec.
        self.assertTrue(any(r.levelno == logging.ERROR for r in timeout_records))

    def test_extraction_failed_emits_warn_with_reason(self) -> None:
        def boom(_: Path) -> dict:
            raise ValueError("synthetic")

        with patch("backend_fastapi.extraction.extract_bronze", side_effect=boom):
            response = self.client.post(
                "/api/v1/uploads",
                files={"file": ("bad.txt", b"bad text", "text/plain")},
            )
        self.assertEqual(response.status_code, 422)
        # The inner exception class is ValueError; logger captures the
        # FutureTimeoutError-or-Exception path's exc class.
        warns = self._messages_with("event=boundary_failure code=extraction_failed")
        self.assertTrue(warns)

    def test_http_error_handler_emits_request_invalid_warn(self) -> None:
        # Hit a route that does not exist; Starlette raises HTTPException(404)
        # which routes through `handle_http_error`.
        response = self.client.get("/api/v1/this-route-does-not-exist")
        self.assertEqual(response.status_code, 404)
        warns = [
            r for r in self.capture.records
            if r.getMessage().startswith("event=request_invalid status=404 code=http_error")
        ]
        self.assertTrue(warns, f"http_error handler did not emit; messages: {[r.getMessage() for r in self.capture.records]!r}")
        self.assertTrue(any(r.levelno == logging.WARNING for r in warns))

    def test_validation_error_handler_emits_warn(self) -> None:
        # Empty filename triggers the validation handler's empty_filename branch.
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("", b"contract text", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        warns = [
            r for r in self.capture.records
            if r.getMessage().startswith("event=request_invalid")
        ]
        self.assertTrue(warns, "validation-error handler did not emit a request_invalid line")

    def test_no_document_content_in_boundary_lines(self) -> None:
        # Upload an oversized payload with recognizable text; assert the text
        # does not appear in any boundary or upload_failed line.
        sentinel = b"SENTINEL_DOCUMENT_CONTENT_THAT_MUST_NOT_LEAK"
        app.state.max_upload_bytes = 8
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("big.txt", sentinel + b" extra padding to exceed limit", "text/plain")},
        )
        self.assertEqual(response.status_code, 413)
        for r in self.capture.records:
            self.assertNotIn(b"SENTINEL_DOCUMENT_CONTENT".decode(), r.getMessage())


if __name__ == "__main__":
    unittest.main()
