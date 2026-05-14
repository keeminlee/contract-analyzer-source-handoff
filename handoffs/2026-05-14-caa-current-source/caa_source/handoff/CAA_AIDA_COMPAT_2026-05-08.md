# Contract Analyzer — AiDa Compatibility Changes
**Date:** 2026-05-08
**Engineer:** Keemin (MUFG)
**On top of:** `CAA_mufg_return_2026-05-06.zip` (GREEN verification package)

---

## Context

After completing the initial MUFG-side verification (all GREEN), a review of the live AiDa frontend and backend repos identified three compatibility gaps that need to be resolved before AiDa marketplace onboarding can proceed. All three are addressed in this package.

---

## Changes

### 1. `AiDa/AiDa-ADO/aid_aida-backend/user_operations/page_operations.py`
**AiDa agent registry card — Contract Analyzer entry corrected**

The card was a placeholder left over from an earlier draft:
- Name typo: "Contract Analyser" → "Contract Analyzer"
- Description was Asset-Locator-adjacent boilerplate — replaced with the actual agent description from DSE1-449
- Added `"owner": "Keemin"`
- Release date updated to `2026-05-15`

This is the record that drives the AiDa Agent Marketplace page (`GET /agent_market_place`) and the homepage LOB cards. The fix needs to land in the AiDa backend repo before onboarding.

---

### 2. `Contracts/contract-analyst-agent-mockup/backend_fastapi/main.py`
**CORS middleware added**

The AiDa frontend (React, served from `aida-dev.mufgamericas.com` and related origins) makes cross-origin API calls. Without CORS headers the browser will block every request to the CAA backend.

Added `CORSMiddleware` with the same origin allowlist used by `Aida_api_registry.py`:
- All AiDa dev/uat/prod origins
- `http://localhost:3000` (AiDa frontend dev server)
- `http://localhost:5173` (CAA Vite dev server)

---

### 3. `Contracts/contract-analyst-agent-mockup/backend_fastapi/main.py`
**Azure AD JWT auth added to protected endpoints**

AiDa's API registry validates Azure AD bearer tokens on all non-trivial endpoints using JWKS. The CAA insights and chat endpoints were unauthenticated — any caller could reach them without a valid AiDa session.

Added a `verify_azure_token` FastAPI dependency that:
- Validates the `Authorization: Bearer <token>` header
- Fetches MUFG Azure AD JWKS (cached by `kid`) and verifies RS256 signature
- Checks issuer against MUFG tenant (`d0deeebd-f1d4-417d-9239-8dc40d182181`)
- Matches the same pattern as `authorizer_code.py` in the AiDa backend

Applied to: `GET /api/v1/analyses/{id}/insights` and `POST /api/v1/analyses/{id}/chat`
Left open (by design): `GET /health` (probe), `POST /api/v1/uploads` (token acquired during upload flow)

**Local dev bypass:** Set `CAA_SKIP_AUTH=1` env var to skip token validation. Existing 37 tests continue to pass without modification.

---

## Files Changed

| File | Repo | Change |
|------|------|--------|
| `user_operations/page_operations.py` | `aid_aida-backend` | Agent card name, description, owner, release date |
| `backend_fastapi/main.py` | `contract-analyst-agent-mockup` | CORS middleware + Azure AD auth dependency |

---

## Test Status

| Check | Result |
|-------|--------|
| CAA backend compile | ✅ Clean |
| CAA backend tests (37) | ✅ 37/37 PASS |
| AiDa backend — no tests affected | ✅ page_operations.py is data-only |

---

## What Still Needs to Happen for Onboarding

1. `page_operations.py` change merged into AiDa backend repo (currently local only)
2. CAA backend deployed to a URL reachable from the AiDa frontend (dev environment)
3. Agent card `"link"` field populated with that deployed URL
4. `CAA_SKIP_AUTH` removed / left unset in deployed environment
5. IAM grant: `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` on `AIH_Operator_SBX`
