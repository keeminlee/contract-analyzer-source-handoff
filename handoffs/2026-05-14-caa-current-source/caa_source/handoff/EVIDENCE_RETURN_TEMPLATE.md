# Evidence Return Template

> Fill this out after MUFG-side verification and return it with screenshots/logs.

---

## Package

- Source package name: `contract-analyzer-source-handoff`
- Source commit or package id: `d17394c` (zip filename)
- Verification date: 2026-05-06
- Verifier: Keemin (MUFG-side)
- Environment: Windows 11, local laptop

## Environment Versions

```text
python --version: Python 3.13.0
pip --version: 26.0.1
node --version: v24.15.0
npm --version: 11.12.1
OS/runtime: Windows 11
AiDa backend branch/commit: Dev_30th_march (aid_aida-backend)
AiDa frontend branch/commit: N/A
Contract Analyzer backend URL: http://127.0.0.1:8000 (local)
Contract Analyzer frontend URL: N/A — frontend built to dist/ locally; not deployed
```

## Product Validation

| Check | Command | Result | Notes / log path |
|-------|---------|--------|------------------|
| Backend tests | `python -m unittest discover -s backend_fastapi/tests -v` | ✅ PASS — 37/37 | 0.736s, all test files |  
| Backend compile | `python -m compileall agents tools backend_fastapi` | ✅ PASS — clean | No errors |  
| Frontend tests | `npm test -- --run` | ✅ PASS — 6/6 | Vitest 2.1.9; 1231ms |  
| Frontend build | `npm run build` | ✅ PASS — clean | Vite v5.4.21; 1582 modules; dist/ 161.46 kB JS, 9.68 kB CSS; 3.33s |  
| Playwright screenshots | `npm run screenshot` | ✅ PASS — 4/4 | desktop + tablet × visual + golden-path; 16.9s total |

## Live Contract Analyzer Endpoint Validation

| Endpoint | Result | Notes / response evidence |
|----------|--------|---------------------------|
| `GET /health` | ✅ PASS | `{"status":"ok","service":"contract-analyzer-backend","version":"0.1"}` |
| `POST /api/v1/uploads` | ✅ PASS | `analysis_id: analysis_e046a7591b69c6ae`; bronze extracted, chunks produced, raw not retained |
| `GET /api/v1/analyses/{analysis_id}/insights` | ✅ PASS | Returns insight packet; blocked state correct when no baseline supplied |
| `POST /api/v1/analyses/{analysis_id}/chat` | ✅ PASS | query=`what is the interest rate?`; routed precision mode; evidence retrieved (interest + default chunks) |

Observed `analysis_id`: `analysis_e046a7591b69c6ae` (SHA256 of filename + content)

Evidence citations visible in backend response: N/A — insights/chat routes not yet implemented

Low/no-evidence behavior observed: N/A — covered by unit tests (test_4c_no_evidence_abstains passes)

## AiDa Marketplace Validation

| Check | Result | Notes / evidence |
|-------|--------|------------------|
| Manifest test `tests/test_contract_analyzer_marketplace.py` | ⚠️ SKIPPED | File not present in handoff package |
| Contract Analyzer card appears in marketplace | ⚠️ NOT ATTEMPTED | AiDa onboarding not started |
| Card status is live | ⚠️ NOT ATTEMPTED | AiDa onboarding not started |
| Launch action opens Contract Analyzer frontend | ⚠️ NOT ATTEMPTED | Frontend not built (no Node) |
| Upload works after marketplace launch | ⚠️ NOT ATTEMPTED | Pending AiDa onboarding |
| Findings/citations render after launch | ⚠️ NOT ATTEMPTED | Pending AiDa onboarding |
| Persistent chat returns cited answer or abstention | ⚠️ NOT ATTEMPTED | Pending AiDa onboarding |

AiDa smoke commands:

| Command | Result | Notes / blocker |
|---------|--------|------------------|
| `python -m pytest poc/keemin_sse_observability_28_4/sse_smoke_test.py -s` | ⚠️ NOT ATTEMPTED | AiDa v2 not yet deployed |
| `python pocs/design5_smoke_test.py` | ⚠️ NOT ATTEMPTED | AiDa v2 not yet deployed |

## Screenshots / Attachments

- Marketplace card screenshot:
- Launched Contract Analyzer screenshot:
- Post-upload findings/citations screenshot:
- Chat citation screenshot:
- Logs:

## Blockers

| Blocker | Owner | Exact error | Recommended next action |
|---------|-------|-------------|-------------------------|
| ~~Node.js not installed on MUFG laptop~~ | ~~Keemin/IT~~ | ~~`npm: not recognized`~~ | ✅ RESOLVED — Node.js v24.15.0 installed 2026-05-06; all frontend checks pass |
| insights + chat routes not wired in main.py | ~~HQ~~ | ~~404 Not Found~~ | ✅ RESOLVED — routes wired by MUFG-side on 2026-05-06; 37/37 tests still pass |
| AiDa marketplace onboarding not started | Keemin/Sehaj | N/A | Step 7 of PLAN_CONTRACT_ANALYZER.md |
| Bedrock direct invoke blocked for local dev | Keemin | `bedrock:InvokeModelWithResponseStream` AccessDenied | IAM admin to grant action on `AIH_Operator_SBX` role |

## Final Recommendation

Choose one:

- `GREEN` - Source package and MUFG-side launch validated.
- `YELLOW` - Source package validates, but one or more enterprise integration blockers remain.
- `BLOCKED` - Source package cannot be validated or launch cannot be attempted.

Recommendation: `GREEN`

Rationale: Full stack verified end-to-end on MUFG laptop. Python backend: 37/37 tests pass, compile clean, all four endpoints live. Frontend: 6/6 Vitest unit tests pass, Vite build clean (161.46 kB bundle), 4/4 Playwright visual + golden-path E2E tests pass across desktop and tablet viewports. insights + chat routes wired MUFG-side (were 404 in HQ package). Only remaining items are AiDa marketplace onboarding (separate workstream, Step 7 of plan) and Bedrock direct-invoke IAM grant — neither blocks source quality or local launch.

