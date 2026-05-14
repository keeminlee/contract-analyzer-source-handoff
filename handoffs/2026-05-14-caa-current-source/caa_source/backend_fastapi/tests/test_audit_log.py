"""Tests for the per-route audit log lines added to `/uploads`,
`/insights`, and `/chat` in Step 4.

Plan tree: docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/
Step:      4_per-route-audit-log
"""

from __future__ import annotations

import logging
import os
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
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self) -> list[str]:
        return [r.getMessage() for r in self.records]


class TestAuditLog(unittest.TestCase):
    def setUp(self) -> None:
        # Step 7 of singlestore migration: `app.state.bronze_storage_dir` is
        # gone (Step 6 discard); the inmemory backend handles persistence.
        os.environ["CAA_SKIP_AUTH"] = "1"
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        app.state.max_upload_bytes = 10 * 1024 * 1024
        app.state.extraction_timeout_seconds = 30
        self.client = TestClient(app)
        self.capture = _CaptureHandler()
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

    def _upload(self, filename: str, content: bytes) -> dict:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": (filename, content, "text/plain")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _audit_lines_for(self, event: str) -> list[str]:
        return [m for m in self.capture.messages() if m.startswith(f"event={event} ")]

    def test_successful_upload_emits_one_event_upload_audit_line(self) -> None:
        self._upload("a.txt", b"alpha")
        lines = self._audit_lines_for("upload")
        self.assertEqual(len(lines), 1, f"expected 1 event=upload line, got {lines!r}")
        line = lines[0]
        for component in ("analysis_id=", "pid=dev", "upn=unknown", "request_id=", "filename_ext=.txt", "size_bytes=5"):
            self.assertIn(component, line)

    def test_upload_audit_line_does_not_contain_filename(self) -> None:
        sensitive = "Acme_Corp_Q4_loan_agreement.txt"
        self._upload(sensitive, b"sensitive payload")
        lines = self._audit_lines_for("upload")
        self.assertEqual(len(lines), 1)
        # The literal sensitive filename must not appear; only the extension.
        self.assertNotIn(sensitive, lines[0])
        self.assertIn("filename_ext=.txt", lines[0])

    def test_failed_upload_does_not_emit_event_upload_audit_line(self) -> None:
        # Unsupported extension fails before the audit line.
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("a.exe", b"MZ", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._audit_lines_for("upload"), [])

    def test_successful_insights_emits_event_insights_read_line(self) -> None:
        upload = self._upload("primary.txt", b"This is a contract for confidentiality and termination.")
        analysis_id = upload["analysis_id"]
        # Reset capture so we only see the insights-read line.
        self.capture.records.clear()
        response = self.client.get(f"/api/v1/analyses/{analysis_id}/insights")
        self.assertEqual(response.status_code, 200)
        lines = self._audit_lines_for("insights_read")
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn(f"analysis_id={analysis_id}", line)
        self.assertIn("baseline_analysis_id=none", line)
        self.assertIn("pid=dev", line)
        self.assertIn("upn=unknown", line)
        self.assertIn("request_id=", line)

    def test_insights_with_baseline_populates_baseline_field(self) -> None:
        primary = self._upload("primary.txt", b"primary contract about confidentiality")
        baseline = self._upload("baseline.txt", b"baseline contract about confidentiality")
        self.capture.records.clear()
        response = self.client.get(
            f"/api/v1/analyses/{primary['analysis_id']}/insights",
            params={"baseline_analysis_id": baseline["analysis_id"]},
        )
        self.assertEqual(response.status_code, 200)
        lines = self._audit_lines_for("insights_read")
        self.assertEqual(len(lines), 1)
        self.assertIn(f"baseline_analysis_id={baseline['analysis_id']}", lines[0])

    def test_successful_chat_emits_event_chat_with_query_text(self) -> None:
        upload = self._upload("primary.txt", b"This is a contract for confidentiality and termination.")
        analysis_id = upload["analysis_id"]
        self.capture.records.clear()
        query = "What are the termination clauses?"
        response = self.client.post(
            f"/api/v1/analyses/{analysis_id}/chat",
            json={"query": query},
        )
        self.assertEqual(response.status_code, 200, response.text)
        lines = self._audit_lines_for("chat")
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn(f"analysis_id={analysis_id}", line)
        self.assertIn("baseline_analysis_id=none", line)
        self.assertIn("pid=dev", line)
        self.assertIn(f"query_len={len(query)}", line)
        # The literal query string must appear (AC 7.2 — user prompt captured).
        self.assertIn("termination clauses", line)

    def test_audit_line_correlates_with_transport_line_via_request_id(self) -> None:
        upload = self._upload("rid.txt", b"correlation contract")
        upload_lines = self._audit_lines_for("upload")
        self.assertEqual(len(upload_lines), 1)
        request_lines = [m for m in self.capture.messages() if m.startswith("event=request ")]
        # Find the request line whose route matches the upload.
        upload_request_lines = [m for m in request_lines if "route=/api/v1/uploads" in m]
        self.assertTrue(upload_request_lines)
        # Pull the request_id substring from each and assert correspondence.
        def _rid(line: str) -> str:
            for token in line.split():
                if token.startswith("request_id="):
                    return token.split("=", 1)[1]
            return ""
        audit_rid = _rid(upload_lines[0])
        request_rid = _rid(upload_request_lines[0])
        self.assertTrue(audit_rid)
        self.assertEqual(audit_rid, request_rid)

    def test_audit_line_does_not_contain_response_body_substrings(self) -> None:
        upload = self._upload(
            "primary.txt",
            b"The Borrower shall pay interest at five percent per annum on the loan principal.",
        )
        analysis_id = upload["analysis_id"]
        self.capture.records.clear()
        query = "What is the interest rate?"
        response = self.client.post(
            f"/api/v1/analyses/{analysis_id}/chat",
            json={"query": query},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        # Pull a candidate response substring from the answer packet.
        # If the packet has any answer_text or chunks, none of those strings
        # may appear in the audit line.
        chat_lines = self._audit_lines_for("chat")
        self.assertEqual(len(chat_lines), 1)
        chat_line = chat_lines[0]
        answer = body.get("answer", {})
        for chunk in answer.get("chunks", []):
            text = chunk.get("text", "")
            if len(text) >= 20:
                self.assertNotIn(
                    text,
                    chat_line,
                    f"chunk text leaked into audit line: {text!r}",
                )
        evidence_packet = body.get("evidence_packet", {})
        for item in evidence_packet.get("evidence_items", []):
            text = item.get("text", "")
            if len(text) >= 20:
                self.assertNotIn(text, chat_line)


if __name__ == "__main__":
    unittest.main()
