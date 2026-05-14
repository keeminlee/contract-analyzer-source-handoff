"""Tests for the auth claims threading on `/uploads`, `/insights`, `/chat`.

After Step 3, all three routes:
- require a valid Azure AD bearer token (or `CAA_SKIP_AUTH=1` in dev),
- bind `claims["pid"]` -> `request.state.pid`,
- bind `claims["upn"]` -> `request.state.upn` (defaulting to "unknown" when missing).

Plan tree: docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/
Step:      3_auth-claims-threading
"""

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
from caa_backend.storage import BronzeStore  # noqa: E402


class TestAuthClaimsThreading(unittest.TestCase):
    def setUp(self) -> None:
        # Step 7 of singlestore migration: `app.state.bronze_storage_dir`
        # removed (Step 6 discard); inmemory backend handles persistence.
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        app.state.max_upload_bytes = 10 * 1024 * 1024
        app.state.extraction_timeout_seconds = 30
        self.client = TestClient(app)

    def tearDown(self) -> None:
        BronzeStore.reset_inmemory()
        app.dependency_overrides.pop(verify_azure_token, None)
        os.environ.pop("CAA_SKIP_AUTH", None)
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def test_upload_returns_401_without_authorization_header(self) -> None:
        # CAA_SKIP_AUTH unset; no Authorization header -> 401 from verify_azure_token.
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("a.txt", b"hello", "text/plain")},
        )
        self.assertEqual(response.status_code, 401)

    def test_insights_returns_401_without_authorization_header(self) -> None:
        response = self.client.get("/api/v1/analyses/abc/insights")
        self.assertEqual(response.status_code, 401)

    def test_chat_returns_401_without_authorization_header(self) -> None:
        response = self.client.post(
            "/api/v1/analyses/abc/chat",
            json={"query": "hi"},
        )
        self.assertEqual(response.status_code, 401)

    def test_caa_skip_auth_yields_dev_pid_on_upload(self) -> None:
        os.environ["CAA_SKIP_AUTH"] = "1"
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("a.txt", b"hello world dev", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)

    def test_dependency_override_lifts_pid_and_upn_to_request_state(self) -> None:
        # Inject claims with both pid and upn; assert upload succeeds (proxy proof
        # that request.state.pid lookup did not raise on a missing key).
        app.dependency_overrides[verify_azure_token] = lambda: {
            "pid": "alice@stub",
            "upn": "alice@example.com",
            "roles": [],
            "groups": [],
        }
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("a.txt", b"alice upload", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)

    def test_missing_upn_defaults_to_unknown(self) -> None:
        # Claims dict without `upn` (the CAA_SKIP_AUTH stub case). The .get fallback
        # must produce "unknown" rather than raise KeyError.
        app.dependency_overrides[verify_azure_token] = lambda: {"pid": "bob"}
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("a.txt", b"bob upload", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
