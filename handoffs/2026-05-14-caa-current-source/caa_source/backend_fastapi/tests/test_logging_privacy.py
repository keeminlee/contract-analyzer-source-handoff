"""Cross-cutting privacy harness for the AiDa-style logging adoption.

Hostile-test framing: assume a future regression introduces response
content into a log line; this test catches it. Substring matching is
deliberate (a partial leak is still a leak).

Plan tree: docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/
Step:      7_test-additions
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


# A fixture document large enough that extracted-text and chunk strings
# exceed 50 chars (so substring matching has real content to look for).
FIXTURE_CONTRACT = """CREDIT AGREEMENT

1 Interest
The Borrower shall pay interest at five percent per annum on the principal sum.

2 Event of Default
Failure to pay principal or interest when due shall be an Event of Default after a thirty day cure period.

3 Financial Covenants
The Borrower must maintain quarterly leverage covenant reporting and timely audited financial statements.
"""


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self) -> list[str]:
        return [r.getMessage() for r in self.records]


class TestLoggingPrivacy(unittest.TestCase):
    def setUp(self) -> None:
        # Step 7 of singlestore migration: `app.state.bronze_storage_dir`
        # removed (Step 6 discard); the inmemory backend handles persistence.
        os.environ["CAA_SKIP_AUTH"] = "1"
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        app.state.max_upload_bytes = 25 * 1024 * 1024
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

    def _upload(self, filename: str, content: bytes) -> dict:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": (filename, content, "text/plain")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _all_log_text(self) -> str:
        # Concatenated single string for substring assertions.
        return "\n".join(self.capture.messages())

    # ---- Presence tests (AC 7.1 / 7.2) -----------------------------

    def test_chat_query_is_logged(self) -> None:
        upload = self._upload("primary.txt", FIXTURE_CONTRACT.encode("utf-8"))
        analysis_id = upload["analysis_id"]
        self.capture.records.clear()
        query = "What are the financial covenants?"
        response = self.client.post(
            f"/api/v1/analyses/{analysis_id}/chat",
            json={"query": query},
        )
        self.assertEqual(response.status_code, 200, response.text)
        chat_lines = [m for m in self.capture.messages() if m.startswith("event=chat ")]
        self.assertEqual(len(chat_lines), 1, f"expected exactly one event=chat line, got {chat_lines!r}")
        self.assertIn("financial covenants", chat_lines[0])

    def test_pid_appears_on_every_authenticated_audit_line(self) -> None:
        upload = self._upload("primary.txt", FIXTURE_CONTRACT.encode("utf-8"))
        analysis_id = upload["analysis_id"]
        self.client.get(f"/api/v1/analyses/{analysis_id}/insights")
        self.client.post(
            f"/api/v1/analyses/{analysis_id}/chat",
            json={"query": "What is the cure period?"},
        )
        for event_name in ("event=upload ", "event=insights_read ", "event=chat "):
            event_lines = [m for m in self.capture.messages() if m.startswith(event_name)]
            self.assertTrue(event_lines, f"missing {event_name!r} line entirely")
            for line in event_lines:
                self.assertIn(
                    "pid=",
                    line,
                    f"{event_name!r} line missing pid= field: {line!r}",
                )

    def test_request_id_correlates_transport_and_audit_lines(self) -> None:
        self._upload("rid.txt", FIXTURE_CONTRACT.encode("utf-8"))
        request_lines = [m for m in self.capture.messages() if m.startswith("event=request ") and "route=/api/v1/uploads" in m]
        upload_lines = [m for m in self.capture.messages() if m.startswith("event=upload ")]
        self.assertEqual(len(request_lines), 1)
        self.assertEqual(len(upload_lines), 1)

        def _rid(line: str) -> str:
            for token in line.split():
                if token.startswith("request_id="):
                    return token.split("=", 1)[1]
            return ""

        self.assertEqual(_rid(request_lines[0]), _rid(upload_lines[0]))

    # ---- Absence tests (AC 7.3 — hostile substring matching) -------

    def test_chat_response_body_is_NOT_logged(self) -> None:
        upload = self._upload("primary.txt", FIXTURE_CONTRACT.encode("utf-8"))
        analysis_id = upload["analysis_id"]
        self.capture.records.clear()
        response = self.client.post(
            f"/api/v1/analyses/{analysis_id}/chat",
            json={"query": "What are the financial covenants?"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        log_text = self._all_log_text()

        # Per the deny-list: answer.packet strings, evidence_packet strings,
        # route.to_dict(), bronze content — none must appear in log lines.
        answer = body.get("answer", {})
        for chunk in answer.get("chunks", []):
            text = chunk.get("text", "")
            if len(text) >= 50:
                self.assertNotIn(
                    text,
                    log_text,
                    f"chunk text leaked into logs: {text!r}",
                )
        for citation in answer.get("citations", []):
            excerpt = citation.get("excerpt", "")
            if len(excerpt) >= 50:
                self.assertNotIn(excerpt, log_text)
        evidence_packet = body.get("evidence_packet", {})
        for item in evidence_packet.get("evidence_items", []):
            text = item.get("text", "")
            if len(text) >= 50:
                self.assertNotIn(text, log_text, f"evidence text leaked: {text!r}")

    def test_upload_filename_is_NOT_logged(self) -> None:
        sensitive = "Acme_Corp_Q4_loan_agreement.pdf"
        # Use a .txt-rooted body so extraction succeeds despite a .pdf name.
        # Use an actual .txt extension to keep the test deterministic; the real
        # property under test is filename-vs-extension. So we use a sensitive .txt name.
        sensitive_txt = "Acme_Corp_Q4_loan_agreement.txt"
        self._upload(sensitive_txt, FIXTURE_CONTRACT.encode("utf-8"))
        log_text = self._all_log_text()
        # Sensitive filename body must not appear; only the extension does.
        self.assertNotIn(
            "Acme_Corp_Q4_loan_agreement",
            log_text,
            "sensitive filename leaked into logs",
        )
        # Extension is allowed and expected.
        self.assertIn("filename_ext=.txt", log_text)

    def test_extracted_text_is_NOT_logged(self) -> None:
        self._upload("primary.txt", FIXTURE_CONTRACT.encode("utf-8"))
        log_text = self._all_log_text()
        # Pull recognizable >=50-char substrings from the fixture and assert absence.
        for sentence in (
            "The Borrower shall pay interest at five percent per annum on the principal sum.",
            "Failure to pay principal or interest when due shall be an Event of Default",
            "The Borrower must maintain quarterly leverage covenant reporting",
        ):
            self.assertNotIn(
                sentence,
                log_text,
                f"extracted-text sentence leaked: {sentence!r}",
            )

    def test_insights_response_is_NOT_logged(self) -> None:
        upload = self._upload("primary.txt", FIXTURE_CONTRACT.encode("utf-8"))
        analysis_id = upload["analysis_id"]
        self.capture.records.clear()
        response = self.client.get(f"/api/v1/analyses/{analysis_id}/insights")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        log_text = self._all_log_text()
        for chunk in body.get("chunks", []):
            text = chunk.get("text", "")
            if len(text) >= 50:
                self.assertNotIn(text, log_text)
        for citation in body.get("citations", []):
            excerpt = citation.get("excerpt", "")
            if len(excerpt) >= 50:
                self.assertNotIn(excerpt, log_text)

    def test_failure_path_emits_no_audit_line(self) -> None:
        # Force oversized.
        app.state.max_upload_bytes = 8
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("big.txt", b"this is too large for the size cap", "text/plain")},
        )
        self.assertEqual(response.status_code, 413)
        upload_audits = [m for m in self.capture.messages() if m.startswith("event=upload ")]
        self.assertEqual(upload_audits, [], f"unexpected success-audit on failure path: {upload_audits!r}")
        boundary = [m for m in self.capture.messages() if m.startswith("event=boundary_failure code=upload_too_large")]
        self.assertEqual(len(boundary), 1)
        upload_failed = [m for m in self.capture.messages() if m.startswith("event=upload_failed")]
        self.assertEqual(len(upload_failed), 1)


if __name__ == "__main__":
    unittest.main()
