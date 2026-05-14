"""Reusable test fixtures for the CAA backend test surface.

Plan tree: docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/
Step:      7_test-suite-update

The new test files (`test_acl.py`, `test_soft_delete.py`, `test_no_local_fs.py`,
`test_singlestore_smoke.py`) import these helpers to stay terse.

Fixtures
--------
- `inmemory_env()` — context manager that flips `CAA_STORAGE_BACKEND=inmemory`
  for the duration of a test and resets the inmemory backend on entry + exit.
- `claims_for(pid)` — returns a synthetic `claims` dict suitable for the
  `verify_azure_token` dependency-override pattern.
- `with_user(app, pid)` — installs a `dependency_overrides` entry on the
  given app for `verify_azure_token` returning `claims_for(pid)`.

Note: this is a `conftest.py` in the unittest-style sense — it is just a
shared helpers module. We do NOT use pytest fixture decorators because the
existing test stack uses `unittest.TestCase`, not pytest's function-style
fixtures. Helpers are imported by name, not auto-injected.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from caa_backend.storage import BronzeStore  # noqa: E402


def claims_for(pid: str, *, upn: str | None = None) -> dict:
    """Return a synthetic Azure AD claims dict for the named pid."""
    claims: dict = {"pid": pid, "roles": [], "groups": []}
    if upn is not None:
        claims["upn"] = upn
    return claims


def with_user(app, pid: str, *, upn: str | None = None):
    """Install a `verify_azure_token` dependency-override on `app` for `pid`.

    The override is a closure that returns `claims_for(pid, upn=upn)`. Caller
    is responsible for popping the override in tearDown.
    """
    # Import inline so this helper does not force the mockup app at import time.
    from backend_fastapi.main import verify_azure_token

    app.dependency_overrides[verify_azure_token] = lambda: claims_for(pid, upn=upn)


@contextlib.contextmanager
def inmemory_env():
    """Context manager that pins `CAA_STORAGE_BACKEND=inmemory` for the body
    and resets the BronzeStore inmemory backend on enter + exit."""
    prior_backend = os.environ.get("CAA_STORAGE_BACKEND")
    os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
    BronzeStore.reset_inmemory()
    try:
        yield
    finally:
        BronzeStore.reset_inmemory()
        if prior_backend is None:
            os.environ.pop("CAA_STORAGE_BACKEND", None)
        else:
            os.environ["CAA_STORAGE_BACKEND"] = prior_backend
