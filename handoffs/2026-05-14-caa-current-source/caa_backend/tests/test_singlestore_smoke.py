"""Optional live-SingleStore smoke test.

Skipped by default. Enable via `CAA_TEST_SINGLESTORE=1` plus working AWS
credentials and Secrets Manager access to `/application/aid/{env}/caa-app-secret`.

Cleans up its own rows by soft-deleting whatever it creates.

Plan tree: docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/
Step:      7_test-suite-update
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from caa_backend.storage import BronzeStore  # noqa: E402


SMOKE_PAYLOAD = {
    "schema_version": "contract_analyzer_bronze_v1",
    "analysis_id": "will-be-overwritten",
    "session_id": "will-be-overwritten",
    "source": {
        "name": "smoke.txt",
        "extension": ".txt",
        "size_bytes": 19,
        "content_type": "text/plain",
    },
    "text": {"full": "smoke contract text", "char_count": 19},
    "extracted_text": "smoke contract text",
    "chunks": [
        {"chunk_id": "bronze_chunk_1", "text": "smoke contract", "span_start": 0, "span_end": 14},
        {"chunk_id": "bronze_chunk_2", "text": "text", "span_start": 15, "span_end": 19},
    ],
    "tables": [],
    "metadata": {},
}


@unittest.skipUnless(
    os.getenv("CAA_TEST_SINGLESTORE") == "1",
    "live SingleStore smoke; requires CAA_TEST_SINGLESTORE=1 and credentials",
)
class TestSingleStoreSmoke(unittest.TestCase):
    """Exercises the real SingleStore branch end-to-end.

    Skipped unless the gating env var is set. When run, the test creates one
    `CAA_ANALYSIS` row + N `CAA_BRONZE_CHUNK` rows, reads them back, and then
    soft-deletes the analysis row to leave the database clean.
    """

    def setUp(self) -> None:
        os.environ["CAA_STORAGE_BACKEND"] = "singlestore"
        self.created_ids: list[tuple[str, str]] = []  # (analysis_id, user_identifier)

    def tearDown(self) -> None:
        # Best-effort cleanup so repeated smoke runs don't accumulate rows.
        for analysis_id, user_identifier in self.created_ids:
            store = BronzeStore()
            try:
                store.soft_delete(analysis_id=analysis_id, user_identifier=user_identifier)
            finally:
                store.close()

    def test_round_trip_against_live_singlestore(self) -> None:
        analysis_id = uuid.uuid4().hex
        user_identifier = f"smoke-{uuid.uuid4().hex[:8]}"
        store = BronzeStore()
        try:
            store.save_bronze(
                analysis_id=analysis_id,
                user_identifier=user_identifier,
                payload=SMOKE_PAYLOAD,
            )
            self.created_ids.append((analysis_id, user_identifier))
        finally:
            store.close()

        store = BronzeStore()
        try:
            loaded = store.load_bronze(analysis_id=analysis_id)
        finally:
            store.close()

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["analysis_id"], analysis_id)
        self.assertEqual(loaded["user_identifier"], user_identifier)
        self.assertEqual(loaded["extracted_text"], "smoke contract text")
        self.assertEqual(len(loaded["chunks"]), 2)


if __name__ == "__main__":
    unittest.main()
