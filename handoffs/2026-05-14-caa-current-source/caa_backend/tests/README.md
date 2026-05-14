# CAA Backend Test Suite

> Plan tree: [`docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/`](../../../docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/)
> Step owning this README: 7 (test-suite-update)

## Layout

| Path | Purpose |
|---|---|
| `caa_backend/tests/test_storage.py` | `BronzeStore` CRUD round-trip + ACL + soft-delete + reset, against the `inmemory` backend. |
| `caa_backend/tests/test_acl.py` | Cross-user ACL matrix on `/insights`, `/chat`, and `baseline_analysis_id`. |
| `caa_backend/tests/test_soft_delete.py` | `DELETE /api/v1/analyses/{id}` happy-path, idempotency, ACL, post-delete read consistency. |
| `caa_backend/tests/test_no_local_fs.py` | Defense check: no file appears under `runtime/bronze/`; legacy symbols absent. |
| `caa_backend/tests/test_singlestore_smoke.py` | Optional live-DB smoke test; skipped unless `CAA_TEST_SINGLESTORE=1`. |
| `caa_backend/tests/conftest.py` | Reusable helpers (`claims_for`, `with_user`, `inmemory_env`). |
| `contract-analyst-agent-mockup/backend_fastapi/tests/` | Existing 11-module suite (37 baseline + logging + singlestore additions). Each file under `caa_backend/tests/` has a 4-line re-export shim here so `unittest discover -s backend_fastapi/tests` picks it up. |

## Env-var contract

| Var | Default | Purpose |
|---|---|---|
| `CAA_STORAGE_BACKEND` | `singlestore` (in deployed envs) | Set to `inmemory` for unit tests + local dev without AWS. All test setUp methods set this. |
| `CAA_SKIP_AUTH` | unset | Set to `1` to bypass `verify_azure_token` and yield a synthetic `{"pid": "dev"}` claim. Used by the legacy 5 modules; new ACL / soft-delete tests use `app.dependency_overrides` instead. |
| `CAA_ENV` | `dev` | Resolves Secrets Manager path: `/application/aid/{env}/caa-app-secret`. Only consulted when `CAA_STORAGE_BACKEND=singlestore`. |
| `CAA_AWS_REGION` | `us-east-1` | Region for the Secrets Manager client. |
| `CAA_TEST_SINGLESTORE` | unset | Set to `1` to opt the smoke-test module into running against a real SingleStore instance. Skipped by default. |

## In-memory vs. live-DB

Default mode for all tests is `CAA_STORAGE_BACKEND=inmemory`. The shim is a process-local dict (see `caa_backend/storage.py::_inmemory_state`) — fully self-contained, no AWS or DB dependency. Tests reset state via `BronzeStore.reset_inmemory()` in setUp and tearDown.

The smoke-test module (`test_singlestore_smoke.py`) optionally exercises the real SingleStore branch when `CAA_TEST_SINGLESTORE=1` and AWS credentials + Secrets Manager access are available. It cleans up its own rows by soft-deleting any analyses it creates. CI never runs it by default.

## Cross-user ACL fixture pattern

For tests that need to simulate distinct users, use `app.dependency_overrides` to inject a synthetic `claims` dict per request. The `with_user(app, pid)` helper in `conftest.py` is sugar for the common case:

```python
from caa_backend.tests.conftest import with_user, inmemory_env

class TestAcrossUsers(unittest.TestCase):
    def setUp(self):
        self._cm = inmemory_env()
        self._cm.__enter__()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(verify_azure_token, None)
        self._cm.__exit__(None, None, None)

    def test_cross_user(self):
        with_user(app, "user-a")
        # ... upload as user-a
        with_user(app, "user-b")
        # ... read as user-b -> 404
```

## Why we don't hit a real DB by default

- AWS credentials and SingleStore network access are not assumed for CI.
- The `inmemory` backend exercises the same public CRUD surface, so contract-level regressions are caught regardless of backend.
- The SingleStore branch is a verbatim port of AiDa's `singleStoreHistory.py` pattern; behavior parity is verified by the optional smoke test when run.

## Running

From `contract-analyst-agent-mockup/`:

```
python -m unittest discover -s backend_fastapi/tests
```

This is the principal-declared per-step verification command. Tests under `caa_backend/tests/` are picked up via re-export shims in `backend_fastapi/tests/`.
