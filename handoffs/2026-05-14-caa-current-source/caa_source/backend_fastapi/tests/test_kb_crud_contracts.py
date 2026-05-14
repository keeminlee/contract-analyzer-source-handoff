from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend_fastapi.main import app, verify_azure_token

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from caa_backend.storage import BronzeStore, KbStore  # noqa: E402


def _claims(pid: str):
    async def _override() -> dict:
        return {"pid": pid, "upn": f"{pid}@example.test", "roles": [], "groups": []}

    return _override


class TestKbCrudContracts(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        app.state.max_upload_bytes = 10 * 1024 * 1024
        app.state.extraction_timeout_seconds = 30
        app.dependency_overrides[verify_azure_token] = _claims("user-a")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def test_kb_routes_require_auth(self) -> None:
        app.dependency_overrides.clear()
        os.environ.pop("CAA_SKIP_AUTH", None)
        response = self.client.get("/api/v1/kb_collections")
        self.assertEqual(response.status_code, 401)

    def test_create_list_get_duplicate_and_delete_collection(self) -> None:
        created = self.client.post("/api/v1/kb_collections", json={"collection_name": "Credit Playbook"})
        self.assertEqual(created.status_code, 201)
        collection = created.json()["collection"]
        collection_id = collection["collection_id"]

        duplicate = self.client.post("/api/v1/kb_collections", json={"collection_name": "credit playbook"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["error"]["code"], "collection_name_in_use")

        listed = self.client.get("/api/v1/kb_collections")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["collections"][0]["collection_id"], collection_id)

        loaded = self.client.get(f"/api/v1/kb_collections/{collection_id}")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["collection"]["members"], [])

        deleted = self.client.delete(f"/api/v1/kb_collections/{collection_id}")
        self.assertEqual(deleted.status_code, 204)
        missing = self.client.get(f"/api/v1/kb_collections/{collection_id}")
        self.assertEqual(missing.status_code, 404)

    def test_collection_acl_collapses_cross_user_to_404(self) -> None:
        created = self.client.post("/api/v1/kb_collections", json={"collection_name": "Credit Playbook"})
        collection_id = created.json()["collection"]["collection_id"]

        app.dependency_overrides[verify_azure_token] = _claims("user-b")
        self.assertEqual(self.client.get(f"/api/v1/kb_collections/{collection_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/kb_collections/{collection_id}").status_code, 404)
        same_name = self.client.post("/api/v1/kb_collections", json={"collection_name": "Credit Playbook"})
        self.assertEqual(same_name.status_code, 201)

    def test_add_member_accepts_single_document_and_zip_is_step5_pending(self) -> None:
        created = self.client.post("/api/v1/kb_collections", json={"collection_name": "Credit Playbook"})
        collection_id = created.json()["collection"]["collection_id"]

        member = self.client.post(
            f"/api/v1/kb_collections/{collection_id}/members",
            files={"file": ("sample.txt", b"The borrower must report covenant compliance.", "text/plain")},
        )
        self.assertEqual(member.status_code, 200)
        payload = member.json()
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(len(payload["member_ids"]), 1)

        loaded = self.client.get(f"/api/v1/kb_collections/{collection_id}")
        self.assertEqual(loaded.json()["collection"]["member_count"], 1)

        zip_response = self.client.post(
            f"/api/v1/kb_collections/{collection_id}/members",
            files={"file": ("sample.zip", b"PK\x03\x04", "application/zip")},
        )
        self.assertEqual(zip_response.status_code, 501)
        self.assertEqual(zip_response.json()["error"]["code"], "zip_ingestion_pending_step_5")

    def test_upload_modes_validate_and_persist_context(self) -> None:
        invalid = self.client.post(
            "/api/v1/uploads",
            data={"mode": "sideways"},
            files={"file": ("invalid.txt", b"Borrower must pay interest.", "text/plain")},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["error"]["code"], "invalid_mode")

        solo_bad = self.client.post(
            "/api/v1/uploads",
            data={"mode": "solo", "comparison_context_id": "not-allowed"},
            files={"file": ("solo.txt", b"Borrower must pay interest.", "text/plain")},
        )
        self.assertEqual(solo_bad.status_code, 422)
        self.assertEqual(solo_bad.json()["error"]["code"], "solo_mode_no_context_allowed")

        baseline = self.client.post(
            "/api/v1/uploads",
            data={"mode": "solo"},
            files={"file": ("baseline.txt", b"Borrower shall pay interest at 5 percent.", "text/plain")},
        )
        self.assertEqual(baseline.status_code, 200)
        baseline_id = baseline.json()["analysis_id"]

        missing_baseline = self.client.post(
            "/api/v1/uploads",
            data={"mode": "one_to_one", "comparison_context_id": "missing"},
            files={"file": ("primary.txt", b"Borrower shall pay interest at 6 percent.", "text/plain")},
        )
        self.assertEqual(missing_baseline.status_code, 422)
        self.assertEqual(missing_baseline.json()["error"]["code"], "baseline_not_found_or_unauthorized")

        one_to_one = self.client.post(
            "/api/v1/uploads",
            data={"mode": "one_to_one", "comparison_context_id": baseline_id},
            files={"file": ("primary.txt", b"Borrower shall pay interest at 6 percent.", "text/plain")},
        )
        self.assertEqual(one_to_one.status_code, 200)
        self.assertEqual(one_to_one.json()["mode"], "one_to_one")
        self.assertEqual(one_to_one.json()["comparison_context_id"], baseline_id)

        insights = self.client.get(f"/api/v1/analyses/{one_to_one.json()['analysis_id']}/insights")
        self.assertEqual(insights.status_code, 200)
        self.assertEqual(insights.json()["source_documents"][1]["analysis_id"], baseline_id)

    def test_kb_mode_requires_ready_owned_collection(self) -> None:
        created = self.client.post("/api/v1/kb_collections", json={"collection_name": "Ready Playbook"})
        collection_id = created.json()["collection"]["collection_id"]

        pending = self.client.post(
            "/api/v1/uploads",
            data={"mode": "kb", "comparison_context_id": collection_id},
            files={"file": ("primary.txt", b"Borrower shall report quarterly.", "text/plain")},
        )
        self.assertEqual(pending.status_code, 422)
        self.assertEqual(pending.json()["error"]["code"], "kb_collection_not_ready_or_unauthorized")

        store = KbStore()
        try:
            self.assertTrue(store.mark_collection_ready(collection_id=collection_id, user_identifier="user-a"))
        finally:
            store.close()

        accepted = self.client.post(
            "/api/v1/uploads",
            data={"mode": "kb", "comparison_context_id": collection_id},
            files={"file": ("primary.txt", b"Borrower shall report quarterly.", "text/plain")},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["mode"], "kb")
        self.assertEqual(accepted.json()["comparison_context_id"], collection_id)


if __name__ == "__main__":
    unittest.main()
