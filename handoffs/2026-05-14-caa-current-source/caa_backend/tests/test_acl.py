"""Cross-user ACL matrix for `/insights` and `/chat` (and baseline parameter).

Plan tree: docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/
Step:      4_read-path-and-acl

Strategy
--------
Per Step 4 spec: simulate distinct users via FastAPI dependency-overrides on
`verify_azure_token` (not by minting real Azure AD JWTs). Each test uploads
as one user (pid=user-a or pid=user-b), then reads back as the same or
different user, and asserts the route returns the **same** `analysis_not_found`
envelope for cross-user reads as for true misses (Locked Decision 10 — no
information leak about analysis_id existence across the user boundary).

Note on co-location: spec called for `caa_backend/tests/test_acl.py`; we
honor that location here AND ensure unittest discovery picks it up by adding
this directory as a discovery target (the per-step verification in the plan
tree's principal command runs `discover -s backend_fastapi/tests`, which would
otherwise miss this file). To keep both discovery roots clean we co-locate a
stub here that ALSO gets imported from the mockup test tree via a thin
`backend_fastapi/tests/test_acl.py` re-export.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Make `caa_backend.storage` importable when invoked directly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Make `backend_fastapi.main` importable (the mockup tree is one level deeper).
_MOCKUP_ROOT = _REPO_ROOT / "contract-analyst-agent-mockup"
if str(_MOCKUP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOCKUP_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend_fastapi.main import app, verify_azure_token  # noqa: E402
from caa_backend.storage import BronzeStore  # noqa: E402


def _claims_for(pid: str) -> dict:
    return {"pid": pid, "roles": [], "groups": []}


def _override(pid: str):
    return lambda: _claims_for(pid)


class TestCrossUserACL(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        # CAA_SKIP_AUTH is intentionally NOT set — we use dependency-overrides
        # so each test can swap the active pid mid-flight.
        os.environ.pop("CAA_SKIP_AUTH", None)
        BronzeStore.reset_inmemory()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(verify_azure_token, None)
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    # -- helpers -----------------------------------------------------------

    def _upload_as(self, pid: str, filename: str, body: bytes) -> str:
        app.dependency_overrides[verify_azure_token] = _override(pid)
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": (filename, body, "text/plain")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["analysis_id"]

    def _read_insights_as(self, pid: str, analysis_id: str, baseline_id: str | None = None):
        app.dependency_overrides[verify_azure_token] = _override(pid)
        url = f"/api/v1/analyses/{analysis_id}/insights"
        if baseline_id is not None:
            url = f"{url}?baseline_analysis_id={baseline_id}"
        return self.client.get(url)

    def _chat_as(self, pid: str, analysis_id: str, query: str = "test query", baseline_id: str | None = None):
        app.dependency_overrides[verify_azure_token] = _override(pid)
        body: dict = {"query": query}
        if baseline_id is not None:
            body["baseline_analysis_id"] = baseline_id
        return self.client.post(f"/api/v1/analyses/{analysis_id}/chat", json=body)

    # -- /insights ACL matrix ---------------------------------------------

    def test_owner_insights_read_returns_200(self) -> None:
        analysis_id = self._upload_as("user-a", "a.txt", b"alpha contract text body")
        response = self._read_insights_as("user-a", analysis_id)
        self.assertEqual(response.status_code, 200)

    def test_cross_user_insights_read_returns_analysis_not_found_404(self) -> None:
        analysis_id = self._upload_as("user-a", "a.txt", b"alpha contract text body")
        response = self._read_insights_as("user-b", analysis_id)
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "analysis_not_found")

    def test_cross_user_envelope_matches_true_miss_envelope(self) -> None:
        # Locked Decision 10: cross-user 404 must be byte-identical in shape to
        # a never-existed 404 so callers cannot use the difference to enumerate
        # analysis_ids belonging to other users.
        analysis_id = self._upload_as("user-a", "a.txt", b"alpha contract text body")
        cross_user = self._read_insights_as("user-b", analysis_id)
        true_miss = self._read_insights_as("user-b", "00000000000000000000000000000000")
        self.assertEqual(cross_user.status_code, true_miss.status_code)
        self.assertEqual(
            cross_user.json().get("error", {}).get("code"),
            true_miss.json().get("error", {}).get("code"),
        )

    def test_soft_deleted_analysis_reads_as_404(self) -> None:
        analysis_id = self._upload_as("user-a", "a.txt", b"alpha contract text body")
        # Direct soft-delete via storage (Step 5 will add the DELETE route).
        store = BronzeStore()
        try:
            self.assertTrue(store.soft_delete(analysis_id=analysis_id, user_identifier="user-a"))
        finally:
            store.close()
        response = self._read_insights_as("user-a", analysis_id)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("error", {}).get("code"), "analysis_not_found")

    # -- /chat ACL matrix --------------------------------------------------

    def test_owner_chat_returns_200(self) -> None:
        analysis_id = self._upload_as("user-a", "a.txt", b"alpha contract text body")
        response = self._chat_as("user-a", analysis_id, query="what is this")
        self.assertEqual(response.status_code, 200)

    def test_cross_user_chat_returns_analysis_not_found_404(self) -> None:
        analysis_id = self._upload_as("user-a", "a.txt", b"alpha contract text body")
        response = self._chat_as("user-b", analysis_id, query="what is this")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("error", {}).get("code"), "analysis_not_found")

    def test_chat_after_soft_delete_returns_404(self) -> None:
        analysis_id = self._upload_as("user-a", "a.txt", b"alpha contract text body")
        store = BronzeStore()
        try:
            store.soft_delete(analysis_id=analysis_id, user_identifier="user-a")
        finally:
            store.close()
        response = self._chat_as("user-a", analysis_id, query="what is this")
        self.assertEqual(response.status_code, 404)

    # -- baseline_analysis_id ACL matrix ----------------------------------

    def test_baseline_owned_returns_200(self) -> None:
        primary_id = self._upload_as("user-a", "primary.txt", b"primary contract text body")
        baseline_id = self._upload_as("user-a", "baseline.txt", b"baseline contract text body")
        response = self._read_insights_as("user-a", primary_id, baseline_id=baseline_id)
        self.assertEqual(response.status_code, 200)

    def test_baseline_cross_user_returns_baseline_not_found_404(self) -> None:
        primary_id = self._upload_as("user-a", "primary.txt", b"primary contract text body")
        # baseline owned by user-b but referenced from user-a's insights call:
        cross_baseline_id = self._upload_as("user-b", "baseline.txt", b"baseline contract text body")
        response = self._read_insights_as("user-a", primary_id, baseline_id=cross_baseline_id)
        self.assertEqual(response.status_code, 404)
        # `/insights` route returns `baseline_not_found` envelope on baseline ACL miss
        # (distinct from primary `analysis_not_found` for caller-side debugging — the
        # baseline existence still doesn't leak because the caller already proved they
        # could read primary; the 404 is gated on baseline ACL).
        self.assertEqual(response.json().get("error", {}).get("code"), "baseline_not_found")

    def test_chat_baseline_cross_user_silently_ignored(self) -> None:
        # `/chat` baseline mismatch is silently dropped (preserves chat continuation
        # semantics; primary ACL is the binding gate per Locked Decision 10).
        primary_id = self._upload_as("user-a", "primary.txt", b"primary contract text body")
        cross_baseline_id = self._upload_as("user-b", "baseline.txt", b"baseline contract text body")
        response = self._chat_as("user-a", primary_id, query="compare", baseline_id=cross_baseline_id)
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
