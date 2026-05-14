# Contract Analyzer Backend Storage Policy

> Last revised: 2026-05-08, in step with the SingleStore bronze migration.
> Plan tree: [`docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/`](../../../docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/)

## V1 Upload Boundary

- Accepted extensions: `.txt`, `.pdf`, `.docx`.
- Maximum upload size: `10 MiB`.
- Extraction timeout: `30 seconds`.
- Virus scanning: out of scope for v1.

## Raw Upload Retention

Raw uploaded document bytes are written only to a per-request temporary file so the bronze extractor can read a path with the correct suffix. The temporary file is deleted before the request returns. The backend does not persist raw uploaded documents in v1.

## Bronze Artifact Persistence

Successful uploads persist a bronze record to **SingleStore** via the `BronzeStore` class in `caa_backend/storage.py`, modelled verbatim on AiDa's `singleStoreHistory.py` pattern. Two tables back the record:

- `CAA_ANALYSIS` — one row per uploaded contract. Carries source metadata (filename, extension, MIME type, byte size), full extracted text as `LONGTEXT`, the schema version (`contract_analyzer_bronze_v1`), the ACL columns described below, and the `EFFECTIVE_FROM_TIMESTAMP` / `As_of_Timestamp` lifecycle columns adopted from AiDa's column convention.
- `CAA_BRONZE_CHUNK` — one row per text chunk produced by `build_text_chunks`. Carries `CHUNK_INDEX`, `CHUNK_TEXT`, `SPAN_START`, `SPAN_END`, and FK to `CAA_ANALYSIS.ANALYSIS_IDENTIFIER`.

`analysis_id` is a server-assigned UUID v4 (32 lowercase hex chars, no hyphens). It replaced the SHA-of-content scheme used pre-migration; the SHA scheme caused cross-user collisions when two users uploaded the same file.

DDL lives at `caa_backend/sql/create_tables.sql`; drop script at `caa_backend/sql/drop_tables.sql`. DDL application is manual / pipeline-driven via AiDa's `TableManager` pattern — not auto-applied at app boot.

The bronze payload returned to API callers continues to surface `extracted_text`, `chunks`, `tables`, `metadata`, and `source` keys. Note that `tables` and `metadata` are passthrough surfaces consumed in-process; v1 does not persist them in `CAA_ANALYSIS` (they re-emerge as empty stand-ins on read). Persistence of those fields is out of scope until v2.

## Identity & Access Control

`USER_IDENTIFIER` on `CAA_ANALYSIS` stores the Azure AD `pid` claim from the request's bearer token (or `"dev"` when `CAA_SKIP_AUTH=1` is set in local dev). The column is conceptually a soft FK to `REF_USER` but is **not** DB-enforced — CAA may not have AiDa's `REF_USER` populated in all environments, so the binding lives in application code.

ACL is enforced on every read and delete:

- `GET /api/v1/analyses/{id}/insights` and `POST /api/v1/analyses/{id}/chat` require `claims["pid"] == row.USER_IDENTIFIER`. Cross-user reads return the same `analysis_not_found` 404 envelope as a true miss — no information leak about whose analyses exist (Locked Decision 10 of the migration plan).
- `DELETE /api/v1/analyses/{id}` carries the same rule, also at the SQL layer (`WHERE USER_IDENTIFIER = %s` in the `UPDATE`); cross-user delete attempts collapse to the same 404 envelope.
- The `baseline_analysis_id` parameter on `/insights` and `/chat` carries the same ACL rule. On `/insights`, baseline ACL miss returns `baseline_not_found`; on `/chat`, baseline mismatch is silently dropped (preserves chat continuation; primary ACL is the binding gate).

## Lifecycle & Soft Delete

`DELETE /api/v1/analyses/{id}` flips `ACTIVE_INDICATOR` from 1 to 0 on the matching `CAA_ANALYSIS` row. Reads and the read-after-delete defense check confirm that soft-deleted rows are filtered (`ACTIVE_INDICATOR = 1` in the WHERE clause). Idempotent — repeated DELETE on the same id collapses to the same `analysis_not_found` 404.

`CAA_BRONZE_CHUNK` rows are NOT cascaded to `ACTIVE_INDICATOR = 0` in v1. Chunks remain at 1 but are unreachable because their parent analysis row is filtered out at read time. Cascade-soft-delete on chunks is documented as a v2 concern (see `caa_backend/storage.py::soft_delete` docstring).

## Connection Posture

`BronzeStore` opens a fresh connection per request and closes it via `try/finally` even on error paths. There is **no connection pooling** — this mirrors AiDa's posture in `singleStoreHistory.py` exactly. A `# TODO(platform-pooling)` comment marks the connection-open site so when the platform-wide pooling work happens in AiDa, CAA gets swept up in the same pass.

Secrets are loaded from AWS Secrets Manager at `/application/aid/{env}/caa-app-secret` (note: `caa-`, not `aida-`) where `{env}` resolves from `CAA_ENV` (default `dev`). The Secrets Manager client uses `verify=False` to honor the corporate-proxy posture documented in `MUFG/aida/notes/AIDA_ENTERPRISE_READINESS_NOTES_2026-05-08.md` §3, §7.

For local dev and unit tests, set `CAA_STORAGE_BACKEND=inmemory` to switch to a process-local dict shim. The shim shares the public CRUD surface (`save_bronze`, `load_bronze`, `soft_delete`, `reset_inmemory`) so contract-level regressions are caught regardless of backend.

## Audit Trail

Bronze writes (`event=upload`), reads (`event=insights_read`, `event=chat`), and deletes (`event=delete`) emit structured log lines on success. Boundary failures emit `event=boundary_failure` and `event=upload_failed`. The full audit-log surface — format conventions, privacy guard, and the `X-Real-IP` precedence ladder — is owned by the sibling `caa-aida-style-logging-adoption` plan tree at `docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/`. This document does **not** define audit-log behavior; it only references the call sites.

## Failure Cleanup

Unsupported, empty, oversized, corrupt, no-text, and timeout failures return structured error JSON and do not write a bronze row to SingleStore. Raw temporary upload bytes are not retained after failure. The route's per-request `BronzeStore` is closed via `try/finally` even on the failure paths.

## Migration History

On 2026-05-08, bronze persistence migrated from local-filesystem JSON files at `backend_fastapi/runtime/bronze/{analysis_id}/bronze.json` to SingleStore-backed storage on `CAA_ANALYSIS` + `CAA_BRONZE_CHUNK`. The migration also (a) replaced the SHA-of-content `analysis_id` scheme with server-assigned UUID v4 hex, eliminating cross-user collisions; (b) introduced per-user ACL via the Azure AD `pid` claim; (c) introduced soft-delete via `ACTIVE_INDICATOR` and the `DELETE /api/v1/analyses/{id}` route. See `docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/` for the plan tree and `caa_backend/MIGRATION_NOTES.md` for the legacy-bronze disposition (decision: discard, since CAA is pre-launch).
