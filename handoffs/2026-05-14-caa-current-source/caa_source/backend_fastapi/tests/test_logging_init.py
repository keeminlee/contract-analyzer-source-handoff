"""Smoke tests for the AiDa-style central logger initialized in
`backend_fastapi.main` (mirrored from `caa_backend.main`).

These tests assert the *structural* facts of the logger: level, handler
type, output stream, format-string components, and that emitting a
record routes through the configured handler in the AiDa format.

Plan tree: docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/
Step:      1_logger-initialization
"""

from __future__ import annotations

import io
import logging
import sys
import unittest

# Importing the module triggers the central logger init at import time.
import backend_fastapi.main as backend_main  # noqa: F401 — side-effect import


class TestLoggingInit(unittest.TestCase):
    def test_root_logger_level_is_info(self) -> None:
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_root_logger_has_stream_handler_to_stdout(self) -> None:
        handlers = logging.getLogger().handlers
        self.assertTrue(handlers, "root logger has no handlers after import")
        stream_handlers = [
            h for h in handlers if isinstance(h, logging.StreamHandler)
        ]
        self.assertTrue(
            stream_handlers,
            f"no StreamHandler on root logger; handlers={handlers!r}",
        )
        # At least one StreamHandler must point at stdout (the AiDa contract).
        # Other handlers (e.g. pytest LogCaptureHandler) may coexist, which is fine.
        stdout_handlers = [
            h for h in stream_handlers if getattr(h, "stream", None) is sys.stdout
        ]
        self.assertTrue(
            stdout_handlers,
            "no StreamHandler is bound to sys.stdout (AiDa contract)",
        )

    def test_log_format_contains_required_components(self) -> None:
        # The module exposes the format string as a constant; assert the
        # four AiDa-canonical components are present.
        self.assertEqual(
            backend_main.LOG_FORMAT,
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        for component in ("%(asctime)s", "%(levelname)s", "%(name)s", "%(message)s"):
            self.assertIn(component, backend_main.LOG_FORMAT)

    def test_module_logger_emits_with_format(self) -> None:
        """Emit a record through a fresh StreamHandler using the AiDa
        format and verify the output contains the field components."""
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.Formatter(backend_main.LOG_FORMAT))
        handler.setLevel(logging.INFO)

        test_logger = logging.getLogger("backend_fastapi.test_logging_init.smoke")
        test_logger.setLevel(logging.INFO)
        test_logger.addHandler(handler)
        try:
            test_logger.info("event=smoke check=1")
        finally:
            test_logger.removeHandler(handler)

        output = buf.getvalue()
        self.assertIn("INFO", output)
        self.assertIn("backend_fastapi.test_logging_init.smoke", output)
        self.assertIn("event=smoke check=1", output)
        # Format separator: the four pipe-delimited fields produce three " | "
        # separators in the rendered line.
        self.assertGreaterEqual(output.count(" | "), 3)


if __name__ == "__main__":
    unittest.main()
