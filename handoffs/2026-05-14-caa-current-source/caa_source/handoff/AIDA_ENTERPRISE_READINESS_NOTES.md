# AiDa — Enterprise Readiness & Portability Findings
**Date:** 2026-05-08
**Purpose:** Reference for Contract Analyzer Agent (CAA) onboarding and any future agent built on the AiDa platform
**Scope:** `aid_aida-backend` + `aid_aida-frontend` as of 2026-05-08

---

## 1. Auth & Identity

**Pattern:** Azure AD JWKS validation using RS256, implemented in `backend_run/authorizer_code.py`.

- One `AzureADAuthorizer` instance created at module level; JWKS fetched on startup, cached by `kid` for 6 hours, config cached 5 minutes
- Token validated on `POST /chat/send` only; homepage, marketplace, and history endpoints are open (acceptable for read-only metadata)
- Frontend uses MSAL (`src/api/authConfig.js`) with `cacheLocation: "sessionStorage"` — correct posture, tokens don't persist across sessions or bleed across tabs
- Token attached to requests via `axiosClient.js` interceptor and `httpService.js` — clean single injection point, no token scatter across components
- `verify_azure_token` FastAPI dependency pattern is copy-paste reusable for any new agent backend — **CAA already uses this**

**Portability notes:**
- Tenant ID (`d0deeebd-f1d4-417d-9239-8dc40d182181`) is hardcoded in `authorizer_code.py` — should be externalized to Secrets Manager or env var for portability across environments
- `api_audiences` comes from Secrets Manager config, which is correct
- New agent backends must implement their own `verify_azure_token` (or import a shared library if one is created); they cannot delegate to the AiDa API registry

---

## 2. Storage — Singlestore

**Pattern:** Credentials from AWS Secrets Manager → `mysql.connector` connection in `page_operations.py` and `singleStoreHistory.py`.

- Secret path: `/application/aid/dev//application/aid/dev/aida-app-secret` (note: double path segment — likely a naming artifact, worth cleaning up)
- All DB operations go through a single connection opened in `__init__` and closed in a `close()` method — no connection pooling; fine for Lambda/thread-per-request but will need pooling under concurrent load
- Schema uses `REF_USER`, `REF_AD_GROUP`, `REF_USER_AD` naming convention (uppercase) — new agent tables should follow this convention
- Chat history (`singleStoreHistory.py`) is keyed to `(user_id, chat_id, session_id)` — **CAA chat is scoped to `analysis_id` and requires its own tables**; do not attempt to reuse the history schema

**Portability notes:**
- The Secrets Manager + `mysql.connector` pattern is fully reusable as-is for any new agent
- New agents need their own table namespace; no shared ORM or migration tooling in place — SQL DDL is in `sql_commands_overall/create_tables.py`
- No connection pooling means each request opens and closes a connection; acceptable now but plan for pooling before high-volume production use

---

## 3. LLM Calls — Bedrock via OAuth/API GW Proxy

**Pattern:** `Bedrock_calls/llm_gen.py` — SSO → AWS Secrets Manager → Azure AD `client_credentials` → MUFG API Gateway → Bedrock (Claude).

- Thread-safe class-level token cache with expiry check — no redundant token fetches under concurrent calls
- Uses `requests` (sync), not native boto3 streaming — works for all current use cases; note if streaming responses are needed in future
- `embedding_gen.py` available for vector embedding calls — same proxy pattern
- SSL: `verify=False` on Secrets Manager client (corporate proxy workaround) — existing pattern, not introducing new risk
- `CAA_CONNECT_PROXY` / `AWS_CA_BUNDLE` env vars needed in deployed environments

**Portability notes:**
- `llm_gen.py` is a direct drop-in for any new agent — copy or import
- Bedrock model ID and Secrets Manager path are the only parameters that vary per deployment
- IAM requirement for **direct boto3**: `bedrock:InvokeModel` / `bedrock:InvokeModelWithResponseStream` on the caller role is NOT required when using the OAuth + API GW proxy pattern — the gateway handles Bedrock access under its own permissions. Direct `boto3.converse_stream()` calls remain IAM-blocked on `AIH_Operator_SBX`; use the proxy path (confirmed working 2026-05-14).
- No streaming support in current pattern; if CAA or future agents need token-by-token streaming, this needs a new implementation path

---

## 4. Agent Marketplace & Backend Registration

**Pattern:** `user_operations/page_operations.py` — `get_homepage_lobs_and_agents()` returns a hardcoded Python dict.

- Marketplace data is **not database-driven** — it is hardcoded in Python. Adding or updating an agent requires a code change and redeploy of the AiDa backend
- Statuses: `"live"` | `"coming-soon"` — no other valid values observed
- `"link"` field is the launch URL; for agents that have their own frontend this should point to the deployed URL of that frontend
- LOB grouping is also hardcoded (`"Operations"`, `"Global Corporate & Investment Banking"`)

**Portability notes:**
- Every new agent requires a manual entry in this file — no self-registration mechanism
- The hardcoded approach is fragile at scale; a DB-driven registry would be a future improvement but is not blocking for now
- CAA's entry is already corrected in the code (name, description, owner, release date) — **needs to be merged into the AiDa backend repo and redeployed to take effect in the marketplace UI**

---

## 5. API Structure & Conventions

**Pattern:** Single FastAPI app in `backend_run/Aida_api_registry.py` — all AiDa endpoints in one process.

- New agents are **not** added to this file — they run as separate FastAPI services with their own deployment
- Standard response shape: plain dicts, no envelope standard (no `{"data": ..., "error": ...}` wrapper) — CAA uses its own consistent error envelope which is fine
- `X-User-Id` header used for history endpoints (alongside JWT); `X-Real-IP` / `X-Forwarded-For` logged for audit
- Logging: standard Python `logging` to stdout, structured with `asctime | levelname | name | message` — **CAA should adopt the same format**

---

## 6. Frontend Architecture

**Pattern:** Create React App (JS, not TypeScript), Axios + fetch, MSAL for auth, React Router for navigation.

- Note: AiDa frontend is **CRA/JS**; CAA frontend is **Vite/TypeScript** — different toolchains. CAA frontend cannot be merged into AiDa frontend without a migration or iframe approach
- Token flow: MSAL acquires token silently on each request via `getAccessToken()` in `httpService.js`, attached as `Authorization: Bearer` by Axios interceptor in `axiosClient.js`
- CAA frontend currently calls backend without auth headers — **must be wired before production**; adopt `getAccessToken()` → `Authorization: Bearer` pattern from `chatService.js`
- AiDa frontend serves as the launch surface for agents (marketplace card → link) but does not embed agent UIs; CAA launches as a separate app at its own URL

---

## 7. Deployment & Environment Management

- **No `.env` files** in repos — all secrets via AWS Secrets Manager, env vars set at deploy time via pipeline (`azure-pipelines.yml`)
- Pipeline: Azure DevOps, YAML-based; CAA will need its own pipeline definition when ready to deploy
- `verify=False` on internal AWS calls (Secrets Manager, boto3) — corporate TLS proxy requires this; `AWS_CA_BUNDLE` / `NODE_EXTRA_CA_CERTS` must be set in all environments
- No Docker files observed — deployment target appears to be EC2 or ECS directly; confirm with Shashi/Remya for CAA

---

## Summary: What CAA Reuses vs. Owns

| Concern | Reuse from AiDa | CAA Owns |
|---------|----------------|----------|
| Azure AD JWT validation | ✅ Pattern (copy `verify_azure_token`) | Instance in `main.py` |
| MSAL token acquisition | ✅ Pattern (`getAccessToken` → `Bearer`) | Wire in CAA frontend |
| Singlestore connection | ✅ Secrets Manager + `mysql.connector` | CAA-specific tables |
| Chat history schema | ❌ Different entity model | `analysis_id`-scoped tables |
| LLM calls | ✅ `llm_gen.py` drop-in | Model ID, Secrets path |
| File upload + extraction | ❌ AiDa has none | Entirely CAA-owned |
| Marketplace card | ✅ Entry in `page_operations.py` | Needs merge + redeploy |
| CORS allowlist | ✅ Same origins | Already added to CAA |
| Logging format | ✅ Adopt same format | Implement in CAA |
| Deployment pipeline | ❌ Separate service | Own Azure DevOps pipeline |
