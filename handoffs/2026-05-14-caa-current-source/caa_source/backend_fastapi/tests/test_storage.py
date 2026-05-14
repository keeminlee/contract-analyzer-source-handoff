"""Tests for `caa_backend.storage.BronzeStore` against the in-memory backend.

The `inmemory` backend exercises the same CRUD surface as the real SingleStore
backend without requiring AWS credentials or a live DB. The smoke test for
the SingleStore backend lives in `test_singlestore_smoke.py` (Step 7).

Plan tree: docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/
Step:      2_storage-class-and-secrets

Note: spec called for `caa_backend/tests/test_storage.py`. We co-locate under
`backend_fastapi/tests/` because the existing test discovery root is here;
moving discovery is out of scope for this plan tree (see follow-up backlog
`caa-collapse-two-main-py-copies.md`).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Add the contract-analyzer-agent root to sys.path so `caa_backend.storage`
# imports cleanly. The mockup test runner uses CWD =
# `contract-analyst-agent-mockup/`; caa_backend is one level up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from caa_backend.storage import BronzeStore, CollectionNameInUse, KbStore  # noqa: E402


SAMPLE_PAYLOAD = {
    "schema_version": "contract_analyzer_bronze_v1",
    "analysis_id": "will-be-overwritten",
    "session_id": "will-be-overwritten",
    "source": {
        "name": "sample.txt",
        "extension": ".txt",
        "size_bytes": 42,
        "content_type": "text/plain",
    },
    "text": {"full": "hello world contract text", "char_count": 25},
    "extracted_text": "hello world contract text",
    "chunks": [
        {"chunk_id": "bronze_chunk_1", "text": "hello world", "span_start": 0, "span_end": 11},
        {"chunk_id": "bronze_chunk_2", "text": "contract text", "span_start": 12, "span_end": 25},
    ],
    "tables": [],
    "metadata": {"key": "value"},
}


class TestBronzeStoreInMemory(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        self.store = BronzeStore()

    def tearDown(self) -> None:
        self.store.close()
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def test_save_returns_analysis_id_unchanged(self) -> None:
        result = self.store.save_bronze(
            analysis_id="aaa111", user_identifier="user-a", payload=SAMPLE_PAYLOAD
        )
        self.assertEqual(result, "aaa111")

    def test_load_after_save_returns_payload_with_user_identifier(self) -> None:
        self.store.save_bronze(
            analysis_id="aaa111", user_identifier="user-a", payload=SAMPLE_PAYLOAD
        )
        loaded = self.store.load_bronze(analysis_id="aaa111")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["analysis_id"], "aaa111")
        self.assertEqual(loaded["user_identifier"], "user-a")
        self.assertEqual(loaded["schema_version"], "contract_analyzer_bronze_v1")
        self.assertEqual(loaded["source"]["name"], "sample.txt")
        self.assertEqual(loaded["extracted_text"], "hello world contract text")
        self.assertEqual(len(loaded["chunks"]), 2)
        self.assertEqual(loaded["chunks"][0]["text"], "hello world")
        self.assertEqual(loaded["text"]["char_count"], 25)
        # `tables` and `metadata` are passthrough in inmemory mode (Locked
        # Decision 1 — they are NOT persisted in the SingleStore branch but
        # are surfaced empty/passthrough in the load shape).
        self.assertIn("tables", loaded)
        self.assertIn("metadata", loaded)

    def test_save_and_load_preserves_mode_context(self) -> None:
        self.store.save_bronze(
            analysis_id="aaa111",
            user_identifier="user-a",
            payload=SAMPLE_PAYLOAD,
            mode="one_to_one",
            comparison_context_id="baseline111",
        )
        loaded = self.store.load_bronze(analysis_id="aaa111")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["analysis_mode"], "one_to_one")
        self.assertEqual(loaded["mode"], "one_to_one")
        self.assertEqual(loaded["comparison_context_identifier"], "baseline111")
        self.assertEqual(loaded["comparison_context_id"], "baseline111")

    def test_load_returns_none_for_unknown_id(self) -> None:
        self.assertIsNone(self.store.load_bronze(analysis_id="does-not-exist"))

    def test_load_returns_none_after_soft_delete(self) -> None:
        self.store.save_bronze(
            analysis_id="aaa111", user_identifier="user-a", payload=SAMPLE_PAYLOAD
        )
        self.assertTrue(
            self.store.soft_delete(analysis_id="aaa111", user_identifier="user-a")
        )
        self.assertIsNone(self.store.load_bronze(analysis_id="aaa111"))

    def test_soft_delete_returns_false_for_unknown_id(self) -> None:
        self.assertFalse(
            self.store.soft_delete(analysis_id="missing", user_identifier="user-a")
        )

    def test_soft_delete_returns_false_for_wrong_user(self) -> None:
        self.store.save_bronze(
            analysis_id="aaa111", user_identifier="user-a", payload=SAMPLE_PAYLOAD
        )
        # ACL defense at the SQL/dict layer: WHERE clause includes USER_IDENTIFIER.
        self.assertFalse(
            self.store.soft_delete(analysis_id="aaa111", user_identifier="user-b")
        )
        # Original row still active for the real owner.
        self.assertIsNotNone(self.store.load_bronze(analysis_id="aaa111"))

    def test_soft_delete_is_idempotent_miss(self) -> None:
        self.store.save_bronze(
            analysis_id="aaa111", user_identifier="user-a", payload=SAMPLE_PAYLOAD
        )
        self.assertTrue(
            self.store.soft_delete(analysis_id="aaa111", user_identifier="user-a")
        )
        # Second call returns False (already soft-deleted).
        self.assertFalse(
            self.store.soft_delete(analysis_id="aaa111", user_identifier="user-a")
        )

    def test_reset_inmemory_clears_state_between_tests(self) -> None:
        self.store.save_bronze(
            analysis_id="aaa111", user_identifier="user-a", payload=SAMPLE_PAYLOAD
        )
        self.assertIsNotNone(self.store.load_bronze(analysis_id="aaa111"))
        BronzeStore.reset_inmemory()
        # New store instance; state is gone.
        self.store.close()
        self.store = BronzeStore()
        self.assertIsNone(self.store.load_bronze(analysis_id="aaa111"))


class TestKbStoreInMemory(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        self.store = KbStore()

    def tearDown(self) -> None:
        self.store.close()
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def test_create_list_get_and_delete_collection(self) -> None:
        collection = self.store.create_collection(user_identifier="user-a", collection_name="Playbook")
        self.assertEqual(collection["collection_name"], "Playbook")
        self.assertEqual(collection["ingestion_status"], "pending")
        self.assertEqual(self.store.list_collections(user_identifier="user-a")[0]["collection_id"], collection["collection_id"])
        loaded = self.store.get_collection(collection_id=collection["collection_id"], user_identifier="user-a")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["members"], [])
        self.assertTrue(self.store.soft_delete_collection(collection_id=collection["collection_id"], user_identifier="user-a"))
        self.assertIsNone(self.store.get_collection(collection_id=collection["collection_id"], user_identifier="user-a"))

    def test_duplicate_active_name_is_rejected_per_user(self) -> None:
        self.store.create_collection(user_identifier="user-a", collection_name="Playbook")
        with self.assertRaises(CollectionNameInUse):
            self.store.create_collection(user_identifier="user-a", collection_name="playbook")
        other = self.store.create_collection(user_identifier="user-b", collection_name="Playbook")
        self.assertEqual(other["user_identifier"], "user-b")

    def test_add_member_and_ready_marker(self) -> None:
        collection = self.store.create_collection(user_identifier="user-a", collection_name="Playbook")
        self.store.save_bronze(analysis_id="aaa111", user_identifier="user-a", payload=SAMPLE_PAYLOAD)
        member = self.store.add_member(
            collection_id=collection["collection_id"],
            user_identifier="user-a",
            analysis_id="aaa111",
            source_filename="sample.txt",
        )
        self.assertIsNotNone(member)
        loaded = self.store.get_collection(collection_id=collection["collection_id"], user_identifier="user-a")
        self.assertEqual(loaded["member_count"], 1)
        self.assertEqual(loaded["members"][0]["analysis_id"], "aaa111")
        self.assertTrue(self.store.mark_collection_ready(collection_id=collection["collection_id"], user_identifier="user-a"))
        ready = self.store.get_collection(collection_id=collection["collection_id"], user_identifier="user-a")
        self.assertEqual(ready["ingestion_status"], "ready")


if __name__ == "__main__":
    unittest.main()
