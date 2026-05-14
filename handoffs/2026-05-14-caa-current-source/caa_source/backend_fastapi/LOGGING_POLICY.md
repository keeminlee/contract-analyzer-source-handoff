# Contract Analyzer Backend Logging Policy

## Purpose

CAA emits structured stdout logs in AiDa's canonical format. This policy enumerates **what is logged**, **what is deliberately not logged**, and the **AC mapping** that binds those choices to Feature 7 of `MUFG/contract-analyzer-agent/handoff/CAA_AC_PROGRESS.md` (AC 7.1 *decisions logged*, AC 7.2 *user details and prompts captured*, AC 7.3 *query results / response content NOT captured*).

This document is reviewer-facing. A MUFG-side governance reviewer (AI Governance / Risk Review) should be able to read it without the surrounding plan tree and understand the privacy posture, the AC traceability, and the operational checklist for adding a new route.

## Logging substrate

- Substrate: Python `logging` standard library.
- Sink: `sys.stdout` only. No file rotation, no Splunk / ELK / CloudWatch backend. Deployment platform captures stdout (mirrors AiDa per `MUFG/aida/notes/AIDA_ENTERPRISE_READINESS_NOTES_2026-05-08.md` §5).
- Formatter: `"%(asctime)s | %(levelname)s | %(name)s | %(message)s"` — copied verbatim from `MUFG/aida/aid_aida-backend/backend_run/Aida_api_registry.py:18-35`.
- Field encoding inside the message string: `key=value` whitespace-separated. Not JSON.
- Default root level: `INFO`. `DEBUG` reserved for noise that should not flood ops by default (e.g. `/health` transport line).
- Initialization site: `caa_backend/main.py` (canonical) and `contract-analyst-agent-mockup/backend_fastapi/main.py` (test target — mirrored verbatim).

## Allow-list — fields logged on purpose

| Field | Source | Where it appears (event) | AC satisfied | Notes |
|---|---|---|---|---|
| `event` | const | every line | 7.1 | `request`, `upload`, `insights_read`, `chat`, `boundary_failure`, `upload_failed`, `request_invalid` |
| `request_id` | middleware | every line emitted by a request lifecycle | 7.1 | UUID4 hex generated server-side if no inbound `X-Request-ID`; echoed on response. Correlation key. |
| `route` | matched FastAPI path template | `request` | 7.1 | Template (`/api/v1/analyses/{analysis_id}/insights`), not interpolated URL. Bounded log cardinality. |
| `method` | HTTP method | `request` | 7.1 | |
| `status` | HTTP status code | `request`, `upload_failed`, `request_invalid` | 7.1 | |
| `latency_ms` | middleware-computed | `request` | 7.1 | Single coarse number. |
| `ip` | `_resolve_client_ip` ladder | `request` | 7.2 | `X-Real-IP` → first hop of `X-Forwarded-For` → `request.client.host` → `"unknown"`. AiDa-pattern parity. |
| `pid` | Azure AD claim | `upload`, `insights_read`, `chat`, `upload_failed` | 7.1, 7.2 | AiDa primary identifier. |
| `upn` | Azure AD claim | `upload`, `insights_read`, `chat` | 7.2 | Human-readability for triage. Defaults to `"unknown"` if missing. |
| `analysis_id` | server-assigned | `upload`, `insights_read`, `chat`, `upload_failed` | 7.1 | Identifier; not document content. |
| `baseline_analysis_id` | request param | `insights_read`, `chat` | 7.1 | Identifier; literal `"none"` when absent. |
| `filename_ext` | `Path(filename).suffix.lower()` | `upload` | 7.1 | Extension only; full filename excluded. |
| `size_bytes` | `len(content)` | `upload` | 7.1 | Byte count. |
| `query_len` | `len(query)` | `chat` | 7.1, 7.2 | Length metadata. |
| `query` | request body | `chat` | 7.2 | **Full text logged via `%r`.** AC 7.2 binding. The prompt is *input*, not *response*. |
| `code` | error code | `boundary_failure`, `upload_failed`, `request_invalid` | 7.1 | Decision identifier for refusal. |
| `timeout_seconds`, `max_bytes`, `received_bytes`, `reason` | metadata on boundary lines | `boundary_failure code=...` | 7.1 | Metadata only; never document content. |

## Deny-list — deliberately omitted (AC 7.3 binding)

The following surfaces are **never** substituted into any logger format string:

- `bronze_result["bronze"]` (and any nested key) — extracted text, chunks, tables, source.
- `bronze_result["bronze"]["extracted_text"]` — full extracted document text.
- `bronze_result["bronze"]["chunks"][i]["text"]` — per-chunk extracted text.
- `evidence_packet["evidence_items"][i]["text"]` — clause text returned to UI.
- `analysis["findings"]`, `analysis["citations"]`, `analysis["risks"]`, `analysis["obligations"]` — grounded outputs.
- `packet["answer_text"]`, `packet["chunks"][i]["text"]`, `packet["citations"][i]["excerpt"]` — model answer surface.
- `route.to_dict()` — router decision payload (precautionary).
- `filename` (full uploaded filename) — filenames may carry sensitive document titles.
- `claims` dict beyond `pid`/`upn` (`roles`, `groups`, `tid`, `name`) — identity overshare.
- Raw uploaded bytes.
- `Authorization` header value.
- Request body of POST routes (middleware never reads body; route handlers only log scoped inputs `query`, `baseline_analysis_id`).

## Severity convention

| Level | Used for |
|---|---|
| `INFO` | Normal lifecycle: every request transport line, every successful per-route audit line. |
| `WARN` | Client-fault failures: `upload_too_large`, `no_extractable_text`, `extraction_failed`, validation errors, generic HTTP errors. Catch-site `event=upload_failed`. |
| `ERROR` | Server-fault failures: `extraction_timeout`. |
| `DEBUG` | Suppressed-by-default noise: `/health` transport line. |

## Correlation

Every line carries `request_id`. To trace one request end-to-end, grep on `request_id=<id>`. Expect:

- 1 `event=request` line (transport).
- 0 or 1 `event=<route_event>` audit line (success path).
- 0 or 1 `event=upload_failed` line (failure path).
- 0..N `event=boundary_failure code=...` lines (one per boundary observed).

The response also carries the same id as the `X-Request-ID` header.

## AC mapping summary

- **AC 7.1 — *Decisions logged*** is satisfied by `event=request` (every non-`/health` request), `event=upload`, `event=insights_read`, `event=chat`, `event=boundary_failure` (one per code), `event=upload_failed`, `event=request_invalid`. Every refusal decision has at least one log line.
- **AC 7.2 — *User details and prompts captured*** is satisfied by `pid` and `upn` on every authenticated audit line, `ip` on every transport line, and the full `query` text on `event=chat`.
- **AC 7.3 — *Response content NOT captured*** is enforced by deliberate code review (no `logger.*` invocation substitutes from response-side surfaces) and by the executable test harness `backend_fastapi/tests/test_logging_privacy.py` (eight tests; substring-matching against extracted-text, chunk-text, evidence-text, sensitive-filename, insight-response strings).

## Operational notes

- **Volume expectation:** 1 transport line + 0–1 audit line + 0–N boundary lines per request. For a healthy CAA at v1 traffic levels, 1–3 INFO lines per request is typical.
- **Retention:** Out-of-scope for this policy. The deployment platform captures stdout and applies its own retention; CAA does no in-process retention.
- **Bedrock LLM-call logging:** Inherited from AiDa's `Bedrock_calls/llm_gen.py` (per readiness notes §3) and is **not duplicated** by this policy. CAA does not log model-call payloads or model responses.

## Adding a new route — checklist

When adding a new route to `caa_backend/main.py`:

1. Add `claims: dict = Depends(verify_azure_token)` to the route signature (unless the route is intentionally public; document why if so).
2. As the first two lines of the route body:
   ```python
   request.state.pid = claims.get("pid", "unknown")
   request.state.upn = claims.get("upn", "unknown")
   ```
3. Just before each successful `JSONResponse(...)` return, emit one INFO audit line in the form `event=<route_name> ...identifiers... pid=%s upn=%s request_id=%s ...`. Pass identifiers and metadata only — never response payload substrings.
4. Mirror the same edits into `contract-analyst-agent-mockup/backend_fastapi/main.py` so the test suite exercises them.
5. Read first: this file (`LOGGING_POLICY.md`) — confirm new fields are in the allow-list or add them.
6. Extend: `backend_fastapi/tests/test_logging_privacy.py` — add a test asserting your new route's response body strings do NOT appear in captured log records.
7. Confirm: full suite green via `python -m unittest discover -s backend_fastapi/tests -v`.

## Out of scope

- Bedrock LLM-call logging (inherited from AiDa).
- Log file rotation, archival, or shipping (deployment platform handles).
- Truncation policy for very long `query` strings (ops-backlog item, not privacy gate).

## Cross-references

- Plan tree: `docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/`
- Privacy review (full borderline-case discussion): `docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/6_privacy-review/PRIVACY_REVIEW.md`
- Sibling policy: `STORAGE_POLICY.md` (this directory)
- Privacy test harness: `backend_fastapi/tests/test_logging_privacy.py`
- AiDa logger reference: `MUFG/aida/aid_aida-backend/backend_run/Aida_api_registry.py:18-35`
- AiDa enterprise readiness notes: `MUFG/aida/notes/AIDA_ENTERPRISE_READINESS_NOTES_2026-05-08.md` §1 (claims), §3 (Bedrock), §5 (logging conventions)

## Provenance

- Authored: 2026-05-08, OMC executor lane (Claude Opus 4.7 1M context)
- Step: `caa-aida-style-logging-adoption/9_logging-policy-doc/`
- Source content promoted from: `6_privacy-review/PRIVACY_REVIEW.md`
- Lane: OMC
