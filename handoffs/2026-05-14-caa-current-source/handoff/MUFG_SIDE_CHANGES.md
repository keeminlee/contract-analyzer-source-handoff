# MUFG-Side Changes — Contract Analyzer Handoff Return

**Date:** 2026-05-06  
**Engineer:** Keemin (MUFG)  
**Against package:** `contract-analyzer-source-handoff-d17394c.zip`

---

## Summary

MUFG received the HQ handoff package, merged it into the canonical mockup location, ran the full verification checklist, and resolved two blockers before returning. All backend and frontend checks now pass.

---

## Changes Made

### 1. `backend_fastapi/main.py` — Wire insights and chat routes

**Problem:** The HQ package shipped `main.py` with only two live routes (`GET /health`, `POST /api/v1/uploads`). The other two routes defined in the spec — `GET /api/v1/analyses/{id}/insights` and `POST /api/v1/analyses/{id}/chat` — were missing entirely, causing 404s.

**Fix:** MUFG-side added:

- **Imports** for the five tool modules that were present in the package but not wired into the API layer:
  ```python
  from tools.contract_insights import analyze_contract_insights
  from tools.insight_packet import build_insight_answer_packet
  from tools.production_spine import build_spine_from_bronze
  from tools.retrieval_evidence import build_evidence_packet
  from tools.semantic_router import route_query
  ```

- **`_load_bronze()` helper** — reads `runtime/bronze/{analysis_id}/bronze.json` from the bronze storage root. Kept internal to `main.py`; no new module created.

- **`GET /api/v1/analyses/{analysis_id}/insights`** — loads primary bronze, optionally loads baseline bronze, builds spines, runs `analyze_contract_insights`, wraps with `build_insight_answer_packet`, returns 200 or 404.

- **`POST /api/v1/analyses/{analysis_id}/chat`** — loads bronze, parses `query` + optional `baseline_analysis_id` from request body, routes via `route_query`, builds evidence packet, builds insight packet, returns composite response with `route`, `evidence_packet`, and `answer`.

**Validation:** All 37 existing backend unit tests pass after wiring (no test changes required). Both routes manually tested against `analysis_id: analysis_e046a7591b69c6ae`.

---

### 2. Environment — `NODE_EXTRA_CA_CERTS` permanently set

**Problem:** Node.js processes (npm, Playwright) failed with `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` due to the MUFG corporate proxy injecting its own TLS cert.

**Fix:** Set `NODE_EXTRA_CA_CERTS` to the MUFG universal CA bundle (`universal_cert.pem`) via `setx` (permanent, user scope). This is a local environment fix only — no source files changed.

---

## Files Changed

| File | Change type | Description |
|------|-------------|-------------|
| `backend_fastapi/main.py` | Source fix | Added 5 imports, `_load_bronze()` helper, insights route, chat route |

No other source files were modified. Test files, tool modules, frontend code, and configs are unchanged from the HQ package.

---

## Verification Results (full detail in `EVIDENCE_RETURN_TEMPLATE.md`)

| Check | Result |
|-------|--------|
| Backend compile | ✅ Clean |
| Backend tests (37) | ✅ 37/37 PASS |
| `GET /health` | ✅ Live |
| `POST /api/v1/uploads` | ✅ Live |
| `GET /api/v1/analyses/{id}/insights` | ✅ Live (MUFG-wired) |
| `POST /api/v1/analyses/{id}/chat` | ✅ Live (MUFG-wired) |
| Frontend Vitest (6) | ✅ 6/6 PASS |
| Frontend Vite build | ✅ Clean — 161.46 kB bundle |
| Playwright E2E/visual (4) | ✅ 4/4 PASS — desktop + tablet |

**Final recommendation: `GREEN`**
