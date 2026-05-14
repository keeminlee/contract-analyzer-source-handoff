"""Soft-delete endpoint tests for `DELETE /api/v1/analyses/{analysis_id}`.

Plan tree: docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/
Step:      5_soft-delete-endpoint

Coverage (per spec):
- Owner DELETE on existing analysis -> 200 + `deleted` payload.
- Owner DELETE on already-soft-deleted analysis -> 404 `analysis_not_found`.
- Owner DELETE on never-existed analysis_id -> 404.
- Cross-user DELETE attempt -> 404 (same envelope; no info leak).
- DELETE without Authorization header -> 401.
- Sequence: upload -> soft-delete -> GET /insights -> 404; POST /chat -> 404.
- Sequence: upload (live) + soft-delete second analysis used as baseline ->
  /insights with that as baseline_analysis_id -> 404 baseline.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_MOCKUP_ROOT = _REPO_ROOT / "contract-analyst-agent-mockup"
if str(_MOCKUP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOCKUP_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend_fastapi.main import app, verify_azure_token  # noqa: E402
from caa_backend.storage import BronzeStore  # noqa: E402


def _override(pid: str):
    return lambda: {"pid": pid, "roles": [], "groups": []}


class TestSoftDeleteEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        os.environ.pop("CAA_SKIP_AUTH", None)
        BronzeStore.reset_inmemory()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(verify_azure_token, None)
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def _upload_as(self, pid: str, filename: str = "a.txt", body: bytes = b"contract text body") -> str:
        app.dependency_overrides[verify_azure_token] = _override(pid)
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": (filename, body, "text/plain")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["analysis_id"]

    def _delete_as(self, pid: str, analysis_id: str):
        app.dependency_overrides[verify_azure_token] = _override(pid)
        return self.client.delete(f"/api/v1/analyses/{analysis_id}")

    # -- happy + idempotent ----------------------------------------------

    def test_owner_delete_returns_200_deleted_payload(self) -> None:
        analysis_id = self._upload_as("user-a")
        response = self._delete_as("user-a", analysis_id)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "deleted")
        self.assertEqual(payload.get("analysis_id"), analysis_id)

    def test_second_delete_returns_404_analysis_not_found(self) -> None:
        analysis_id = self._upload_as("user-a")
        self._delete_as("user-a", analysis_id)
        response = self._delete_as("user-a", analysis_id)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("error", {}).get("code"), "analysis_not_found")

    def test_delete_unknown_id_returns_404_analysis_not_found(self) -> None:
        # Need an authenticated user even for the not-found path.
        response = self._delete_as("user-a", "00000000000000000000000000000000")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("error", {}).get("code"), "analysis_not_found")

    def test_cross_user_delete_returns_404_same_envelope(self) -> None:
        analysis_id = self._upload_as("user-a")
        response = self._delete_as("user-b", analysis_id)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("error", {}).get("code"), "analysis_not_found")

    def test_delete_without_auth_returns_401(self) -> None:
        # No dependency override; mockup `verify_azure_token` rejects without
        # Authorization header. Tear down any previous override from setUp.
        app.dependency_overrides.pop(verify_azure_token, None)
        response = self.client.delete("/api/v1/analyses/00000000000000000000000000000000")
        self.assertEqual(response.status_code, 401)

    # -- read-path-after-delete consistency ------------------------------

    def test_insights_after_soft_delete_returns_404(self) -> None:
        analysis_id = self._upload_as("user-a")
        self._delete_as("user-a", analysis_id)
        # /insights as the same authenticated user
        app.dependency_overrides[verify_azure_token] = _override("user-a")
        response = self.client.get(f"/api/v1/analyses/{analysis_id}/insights")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("error", {}).get("code"), "analysis_not_found")

    def test_chat_after_soft_delete_returns_404(self) -> None:
        analysis_id = self._upload_as("user-a")
        self._delete_as("user-a", analysis_id)
        app.dependency_overrides[verify_azure_token] = _override("user-a")
        response = self.client.post(
            f"/api/v1/analyses/{analysis_id}/chat",
            json={"query": "anything"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("error", {}).get("code"), "analysis_not_found")

    def test_baseline_pointing_at_soft_deleted_returns_baseline_not_found(self) -> None:
        primary_id = self._upload_as("user-a", "primary.txt", b"primary contract body")
        baseline_id = self._upload_as("user-a", "baseline.txt", b"baseline contract body")
        self._delete_as("user-a", baseline_id)
        app.dependency_overrides[verify_azure_token] = _override("user-a")
        response = self.client.get(
            f"/api/v1/analyses/{primary_id}/insights",
            params={"baseline_analysis_id": baseline_id},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("error", {}).get("code"), "baseline_not_found")


if __name__ == "__main__":
    unittest.main()
