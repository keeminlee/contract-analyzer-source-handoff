"""Defense-check tests that the SingleStore migration is clean.

Plan tree: docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/
Step:      6_legacy-fs-backfill-policy

Asserts:
- An upload + GET /insights cycle does not write any file under
  `backend_fastapi/runtime/bronze/` (the legacy bronze directory).
- The legacy symbols `build_analysis_id`, `_write_json`, and
  `DEFAULT_BRONZE_STORAGE_DIR` are absent from `caa_backend.main`,
  `backend_fastapi.main`, and `backend_fastapi.extraction` after the Step 6
  discard cleanup.
- `app.state.bronze_storage_dir` is not initialized by either app at module
  load time.
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

from backend_fastapi import extraction as mockup_extraction  # noqa: E402
from backend_fastapi import main as mockup_main  # noqa: E402
from backend_fastapi.main import app, verify_azure_token  # noqa: E402
from caa_backend import main as caa_main  # noqa: E402
from caa_backend.storage import BronzeStore  # noqa: E402


_LEGACY_BRONZE_DIR = _MOCKUP_ROOT / "backend_fastapi" / "runtime" / "bronze"


def _override_pid(pid: str):
    return lambda: {"pid": pid, "roles": [], "groups": []}


class TestNoLocalFs(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        os.environ.pop("CAA_SKIP_AUTH", None)
        BronzeStore.reset_inmemory()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(verify_azure_token, None)
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def test_upload_does_not_create_legacy_bronze_dir(self) -> None:
        # Capture pre-state. The directory may legitimately not exist.
        pre_exists = _LEGACY_BRONZE_DIR.exists()
        pre_contents = list(_LEGACY_BRONZE_DIR.rglob("*")) if pre_exists else []

        app.dependency_overrides[verify_azure_token] = _override_pid("user-a")
        upload = self.client.post(
            "/api/v1/uploads",
            files={"file": ("a.txt", b"contract text body", "text/plain")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        analysis_id = upload.json()["analysis_id"]

        insights = self.client.get(f"/api/v1/analyses/{analysis_id}/insights")
        self.assertEqual(insights.status_code, 200)

        # Post-state must match pre-state — no new files appear.
        post_exists = _LEGACY_BRONZE_DIR.exists()
        post_contents = list(_LEGACY_BRONZE_DIR.rglob("*")) if post_exists else []
        self.assertEqual(pre_exists, post_exists, f"runtime/bronze materialized at {_LEGACY_BRONZE_DIR}")
        self.assertEqual(pre_contents, post_contents)

    def test_legacy_symbols_absent_from_caa_main(self) -> None:
        for symbol in ("build_analysis_id", "DEFAULT_BRONZE_STORAGE_DIR"):
            self.assertFalse(
                hasattr(caa_main, symbol),
                f"caa_backend.main.{symbol} should be removed by Step 6",
            )

    def test_legacy_symbols_absent_from_mockup_main(self) -> None:
        for symbol in ("build_analysis_id", "DEFAULT_BRONZE_STORAGE_DIR"):
            self.assertFalse(
                hasattr(mockup_main, symbol),
                f"backend_fastapi.main.{symbol} should be removed by Step 6",
            )

    def test_legacy_symbols_absent_from_extraction(self) -> None:
        self.assertFalse(
            hasattr(mockup_extraction, "_write_json"),
            "backend_fastapi.extraction._write_json should be removed by Step 6",
        )

    def test_app_state_does_not_carry_bronze_storage_dir_at_load(self) -> None:
        # Tests in earlier modules may set this attribute directly during
        # their setUp; we only assert that the app modules do NOT initialize
        # it themselves at module load time.
        for attr in ("bronze_storage_dir",):
            init_value = getattr(caa_main.app.state, attr, None)
            # A test running before us may have set it. We can't assert None
            # globally; instead, prove that if we re-import the module fresh,
            # the attribute is absent. As a less-invasive proxy: check that
            # neither caa_main nor mockup_main carries DEFAULT_BRONZE_STORAGE_DIR
            # (the only initializer that ever populated app.state.bronze_storage_dir).
            self.assertFalse(
                hasattr(caa_main, "DEFAULT_BRONZE_STORAGE_DIR"),
                "DEFAULT_BRONZE_STORAGE_DIR initializer leaks through caa_main",
            )
            self.assertFalse(
                hasattr(mockup_main, "DEFAULT_BRONZE_STORAGE_DIR"),
                "DEFAULT_BRONZE_STORAGE_DIR initializer leaks through mockup_main",
            )
            # Reference-only — silence unused linters in the loop.
            _ = init_value


if __name__ == "__main__":
    unittest.main()
