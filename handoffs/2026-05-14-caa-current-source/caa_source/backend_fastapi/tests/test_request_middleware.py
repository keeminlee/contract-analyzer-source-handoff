"""Tests for the AiDa-style request_logging_middleware in
`backend_fastapi.main` (mirrored from `caa_backend.main`).

Plan tree: docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/
Step:      2_request-middleware
"""

from __future__ import annotations

import logging
import os
import re
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend_fastapi.main import app

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from caa_backend.storage import BronzeStore  # noqa: E402


class _CaptureHandler(logging.Handler):
    """Lightweight handler that buffers all records for assertion."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages_at(self, level: int) -> list[str]:
        return [r.getMessage() for r in self.records if r.levelno == level]


class TestRequestMiddleware(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CAA_SKIP_AUTH"] = "1"
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        self.client = TestClient(app)
        self.capture = _CaptureHandler()
        # Attach to the module logger that emits the request line.
        self.target_logger = logging.getLogger("backend_fastapi.main")
        self.target_logger.addHandler(self.capture)
        self.previous_level = self.target_logger.level
        self.target_logger.setLevel(logging.DEBUG)

    def tearDown(self) -> None:
        self.target_logger.removeHandler(self.capture)
        self.target_logger.setLevel(self.previous_level)
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_SKIP_AUTH", None)
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def _request_lines(self) -> list[str]:
        return [
            r.getMessage()
            for r in self.capture.records
            if r.getMessage().startswith("event=request")
        ]

    def test_non_health_request_emits_one_info_request_line(self) -> None:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("hello.txt", b"hello world", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        info_lines = [
            r.getMessage()
            for r in self.capture.records
            if r.levelno == logging.INFO and r.getMessage().startswith("event=request")
        ]
        self.assertEqual(len(info_lines), 1, f"expected 1 info request line, got {info_lines!r}")
        line = info_lines[0]
        for component in ("request_id=", "route=/api/v1/uploads", "method=POST", "status=200", "latency_ms=", "ip="):
            self.assertIn(component, line)

    def test_inbound_request_id_header_is_preserved(self) -> None:
        rid = "abc123-correlation-id"
        response = self.client.get("/health", headers={"X-Request-ID": rid})
        self.assertEqual(response.headers.get("X-Request-ID"), rid)
        # /health logs at DEBUG; the same rid must appear there.
        debug_lines = [
            r.getMessage()
            for r in self.capture.records
            if r.levelno == logging.DEBUG and r.getMessage().startswith("event=request")
        ]
        self.assertTrue(debug_lines)
        self.assertTrue(any(f"request_id={rid}" in line for line in debug_lines))

    def test_missing_request_id_generates_uuid4_hex(self) -> None:
        response = self.client.get("/health")
        rid = response.headers.get("X-Request-ID", "")
        # uuid4().hex is 32 lowercase hex chars
        self.assertRegex(rid, r"^[0-9a-f]{32}$")
        debug_lines = [
            r.getMessage()
            for r in self.capture.records
            if r.levelno == logging.DEBUG and r.getMessage().startswith("event=request")
        ]
        self.assertTrue(any(f"request_id={rid}" in line for line in debug_lines))

    def test_route_field_is_path_template_not_interpolated_url(self) -> None:
        # Hit insights with an arbitrary id so no bronze exists; route still resolves.
        response = self.client.get(
            "/api/v1/analyses/abc/insights",
        )
        # Whether the response is 200 or 404, the matched route template is the path the
        # FastAPI router resolved to.
        info_lines = [
            r.getMessage()
            for r in self.capture.records
            if r.levelno == logging.INFO and r.getMessage().startswith("event=request")
        ]
        self.assertTrue(info_lines)
        line = info_lines[0]
        self.assertIn("route=/api/v1/analyses/{analysis_id}/insights", line)
        self.assertNotIn("/api/v1/analyses/abc/insights", line)
        self.assertEqual(response.status_code, 404)

    def test_ip_ladder_x_real_ip_takes_precedence(self) -> None:
        self.client.get(
            "/health",
            headers={
                "X-Real-IP": "10.0.0.1",
                "X-Forwarded-For": "10.0.0.2, 10.0.0.3",
            },
        )
        debug_lines = [
            r.getMessage()
            for r in self.capture.records
            if r.levelno == logging.DEBUG and r.getMessage().startswith("event=request")
        ]
        self.assertTrue(any(" ip=10.0.0.1" in line for line in debug_lines))

    def test_ip_ladder_x_forwarded_for_first_hop_when_no_real_ip(self) -> None:
        self.client.get(
            "/health",
            headers={"X-Forwarded-For": "10.0.0.2, 10.0.0.3"},
        )
        debug_lines = [
            r.getMessage()
            for r in self.capture.records
            if r.levelno == logging.DEBUG and r.getMessage().startswith("event=request")
        ]
        self.assertTrue(any(" ip=10.0.0.2" in line for line in debug_lines))

    def test_ip_ladder_falls_back_to_request_client_host(self) -> None:
        self.client.get("/health")
        debug_lines = [
            r.getMessage()
            for r in self.capture.records
            if r.levelno == logging.DEBUG and r.getMessage().startswith("event=request")
        ]
        # TestClient default is testclient -> request.client.host == "testclient"
        self.assertTrue(any(" ip=testclient" in line for line in debug_lines))

    def test_health_does_not_emit_at_info(self) -> None:
        self.client.get("/health")
        info_lines = [
            r.getMessage()
            for r in self.capture.records
            if r.levelno == logging.INFO and r.getMessage().startswith("event=request")
        ]
        self.assertEqual(info_lines, [])

    def test_request_id_attached_to_request_state_before_handler(self) -> None:
        # Successful upload runs through the full middleware -> handler -> middleware
        # cycle. Audit-line tests in Step 4 will assert correlation; here we assert the
        # response header echo as the observable proof.
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("rid.txt", b"correlation check", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        rid = response.headers.get("X-Request-ID", "")
        self.assertRegex(rid, r"^[0-9a-f]{32}$")


if __name__ == "__main__":
    unittest.main()
