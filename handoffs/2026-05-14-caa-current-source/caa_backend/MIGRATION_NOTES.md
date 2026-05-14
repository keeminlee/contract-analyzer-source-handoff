# CAA Bronze Migration Notes — Local-FS to SingleStore (2026-05-08)

> **Plan tree:** [`docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/`](../../docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/)
> **Step owning this memo:** 6 (legacy-fs-backfill-policy)
> **Disposition:** `discard`

## Inventory at migration time

| Field | Value |
|---|---|
| Path scanned | `MUFG/contract-analyzer-agent/contract-analyst-agent-mockup/backend_fastapi/runtime/bronze/` |
| Files found | `0` (directory absent on disk; entry is git-ignored via `.gitignore` line `backend_fastapi/runtime/`) |
| Total bytes | `0` |
| Oldest mtime | `n/a` |
| Newest mtime | `n/a` |

The directory had been used as scratch for local-dev `extract_and_store_bronze` writes before the SingleStore migration. No checked-in artifacts existed; CI never persisted to it; the `.gitignore` entry confirms its intended ephemeral / test-only role.

## Decision

**`discard`**, per root plan Locked Decision 9.

## Rationale

- CAA is pre-launch. AiDa marketplace `release_date` is `2026-05-15` (per `MUFG/aida/aid_aida-backend/user_operations/page_operations.py::get_homepage_lobs_and_agents` Contract Analyzer entry).
- No production user analyses exist anywhere; the local-fs `runtime/bronze/` artifacts that would have existed in dev or test environments were tied to the `analysis_id = SHA-of-content` scheme that is itself being retired. Re-keying them to UUID v4 would require manufacturing a `USER_IDENTIFIER` (the SHA scheme has no owner-binding), which would corrupt the per-user ACL invariant the migration is designed to introduce.
- The cleanup work is mechanical: drop the `# DEPRECATED`-marked code paths and orphan references. No data loss; no migration script needed.

## Action taken

The following code surfaces are removed (or converted to no-ops) by this step:

| Symbol / surface | File | Disposition |
|---|---|---|
| `build_analysis_id(filename, content)` | `caa_backend/main.py`, `backend_fastapi/main.py` | **Removed.** SHA-of-content scheme is the cross-user-collision bug the migration killed. No callers remain. |
| `_write_json(path, payload)` | `backend_fastapi/extraction.py` | **Removed.** Sole caller was the deprecated local-fs branch in `extract_and_store_bronze`. |
| Local-fs branch in `extract_and_store_bronze` | `backend_fastapi/extraction.py` | **Removed.** Function signature simplified — `storage_root` parameter dropped entirely; function always returns the SingleStore-branch shape (`artifact = {"storage_backend": "singlestore", "raw_upload_retention": ...}`). |
| `DEFAULT_BRONZE_STORAGE_DIR` constant | `caa_backend/main.py`, `backend_fastapi/main.py` | **Removed.** No callers after the local-fs branch deletion. |
| `app.state.bronze_storage_dir` initializer | `caa_backend/main.py`, `backend_fastapi/main.py` | **Removed.** Test fixtures in Step 7 sweep clean. |
| `# DEPRECATED` markers introduced in Steps 3-5 | All sites | **Resolved by deletion** of the deprecated symbol — no marker remains. |

After this step, no code path in `caa_backend/` or the mockup tree reads or writes `runtime/bronze/`. Step 7's test-suite sweep verifies via `test_no_local_fs.py`.

## Backlog

No backlog item filed for the discarded data (none existed; nothing to track for soak / cleanup). The `caa-collapse-two-main-py-copies.md` backlog item (filed during 2026-05-08 logging coherence pass) remains the open container for the parallel-`main.py` posture; it is not affected by this step.

## Provenance

- Agent Platform: `unknown` (Claude Opus 4.7 1M context, OMC executor lane)
- Workflow Agent: `ExecuteRecurse`
- Transcript Source: `Unknown`
- Transcript Path: `PENDING transcript extraction`
- Session ID: `aff38a8e4bcaf9b47`
- Ledger File: `NOT RECORDED`
