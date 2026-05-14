# Contract Analyzer — Acceptance Criteria & Verification Progress
**Date:** 2026-05-06  
**Epic:** DSE1-449 | Release 3 — New Agents: Contract Analyzer  
**Source:** `AiDa Post 4-30 Features (Updated Backlog)` — Contract Analyzer D1 / D2 rows  
**Verified against:** `contract-analyzer-source-handoff-d17394c.zip` + MUFG-side wiring

> ACs are distilled from backlog feature descriptions. Each AC maps to a specific test, endpoint call, or code artifact that was verified during MUFG-side acceptance on 2026-05-06.

---

## Feature 1 — User File Upload
**Backlog:** "Ability for users to upload their own documents such as loan agreements, bond agreements, credit agreements and draft contracts" — 3 days, D1

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 1.1 | User can upload a loan agreement | ✅ PASS | `doc_type_inference.py` classifies loan; `POST /api/v1/uploads` accepts `.pdf`/`.docx`/`.txt` |
| 1.2 | User can upload a bond agreement | ✅ PASS | Same pipeline; bond inferred from content |
| 1.3 | User can upload a credit agreement | ✅ PASS | Same pipeline; credit inferred |
| 1.4 | User can upload a draft contract | ✅ PASS | Same pipeline; draft inferred |
| 1.5 | Unsupported file types are rejected with a clear error | ✅ PASS | Vitest: "shows unsupported upload errors" — 400 + `unsupported_extension` code returned |
| 1.6 | Upload returns a stable, unique `analysis_id` | ✅ PASS | SHA-256 of filename + content; live: `analysis_e046a7591b69c6ae` |
| 1.7 | Raw file content is not retained post-processing | ✅ PASS | Upload response: `"raw": false`; only bronze JSON stored |

---

## Feature 2 — Comparison Agent
**Backlog:** "Develop comparison agent that shows changes from prior agreements to current agreement" — 3 days, D1

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 2.1 | User can supply a prior/baseline agreement alongside the primary document | ✅ PASS | `baseline_analysis_id` param wired in `GET /insights` and `POST /chat`; two uploads produce two `analysis_id`s that can be paired |
| 2.2 | Agent surfaces differences between prior and current agreement | ✅ PASS | `comparison_policy.py` defines diff rules; comparison route active in `semantic_router.py` when baseline resolved |
| 2.3 | Differences are traceable to specific clauses with citations | ✅ PASS | `evidence_generation.py` produces clause-level evidence items in comparison mode; Vitest: "keeps chat messages and renders cited answers" PASS |

---

## Feature 3 — Evidence-Backed Insights
**Backlog:** "Evidence backed insights to support credit analysis and risk assessment" — 2 days, D1

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 3.1 | Every insight is backed by clause-level citations | ✅ PASS | `insight_packet.py` attaches evidence chunks to every insight; Vitest: "uploads a contract, renders findings, connects citations" PASS |
| 3.2 | Agent abstains rather than hallucinating when evidence is insufficient | ✅ PASS | Backend test `test_4c_no_evidence_abstains` PASS (37/37); Vitest: "renders low-evidence fallback" PASS |
| 3.3 | Insights cover key terms, covenants, and obligations | ✅ PASS | `contract_insights.py` extracts all three categories; `production_spine.py` maps contract sections to clause types |
| 3.4 | Chat questions return evidence-backed cited answers | ✅ PASS | `POST /chat` returns `route`, `evidence_packet`, `answer` with citations; live test against `analysis_e046a7591b69c6ae` PASS |

---

## Feature 4 — Contract Identification
**Backlog:** "Identify Contracts to be used by Contract Analyzer including loan, bond, credit and draft agreements" — 2 days, D1

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 4.1 | System classifies uploaded document as loan, bond, credit, or draft | ✅ PASS | `doc_type_inference.py` — all four types implemented |
| 4.2 | Classification informs spine construction (not hardcoded) | ✅ PASS | `production_spine.py` is contract-type-agnostic; spine built from inferred type, not preset template |

---

## Feature 5 — AiDa Marketplace Onboarding / Bedrock
**Backlog:** "Onboarding Contract Analyzer agent in AiDa. Convert to work with Bedrock" — 5 days, D1

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 5.1 | Bedrock proxy client scaffolded | ✅ PASS | `tools/aida_proxy_client.py` present; MUFG API GW/OAuth pattern ready to wire |
| 5.2 | Agent card visible in AiDa marketplace | ❌ NOT STARTED | AiDa v2 marketplace onboarding not begun |
| 5.3 | Launch action opens Contract Analyzer UI | ❌ NOT STARTED | Pending marketplace onboarding |
| 5.4 | LLM calls routed through Bedrock via OAuth/API GW proxy | ⏳ SCAFFOLDED | `aida_proxy_client.py` exists; live calls blocked on IAM grant (`bedrock:InvokeModelWithResponseStream` on `AIH_Operator_SBX`) |
| 5.5 | All existing capabilities work post-onboarding | ❌ NOT TESTED | Pending Steps 5.2–5.4 |

---

## Feature 6 — AD Groups
**Backlog:** "Set up and populate AD groups for the agent" — 5 days, D1/D2

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 6.1 | AD group(s) created for Contract Analyzer agent | ❌ NOT STARTED | Blocked on architecture review |
| 6.2 | Business users added to AD groups | ❌ NOT STARTED | Blocked on AC-6.1 |

---

## Feature 7 — Logging and Monitoring
**Backlog:** "Logging and Monitoring — Agents decisions, user details and prompts must be logged" — 3 days, D1

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 7.1 | Agent decisions are logged per request | ❌ NOT STARTED | No logging implementation in handoff package |
| 7.2 | User details and prompts are captured in logs | ❌ NOT STARTED | Not present in handoff package |
| 7.3 | Query results / response content are NOT captured in logs (data privacy) | ❌ NOT STARTED | Must be enforced when logging is implemented |

> **Blocker note:** This feature must be completed before any production AiDa deployment. It is the highest-priority unstarted item.

---

## Feature 8 — Architecture, Flow Diagram, and ATX
**Backlog:** "Architecture, Flow Diagram and ATX for the agent" — 9 days (draft 2d + internal review 2d + architecture review 5d)

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 8.1 | Architecture diagram drafted | ⏳ PARTIAL | HQ handoff includes `handoff/` docs; formal MUFG ATX not yet submitted |
| 8.2 | Reviewed with internal team (Shashi/Shailesh/Samyak) | ❌ NOT STARTED | — |
| 8.3 | Reviewed with architecture team (Remya/Anirban) | ❌ NOT STARTED | — |

---

## Feature 9 — AI Governance and Model Risk Review
**Backlog:** "AI Governance and Model Risk requirements and review" — 5 days, D1 | Owner: Erik/Bindu/Chris

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 9.1 | AIC submission form completed and submitted | ❌ NOT STARTED | — |
| 9.2 | Review meeting scheduled and completed | ❌ NOT STARTED | — |

---

## Feature 10 — Data Storage in Singlestore (D2)
**Backlog:** "Data storage in Singlestore — Discuss with Bastin and Shailesh requirements per use case and changes in Data Design" — D2

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| 10.1 | Data design reviewed with Bastin/Shailesh | ❌ NOT STARTED | Current storage: file-based `runtime/bronze/` |
| 10.2 | Bronze/spine data persisted to Singlestore | ❌ NOT STARTED | Pending design |

---

## Summary Scorecard

| Feature | ACs Total | ✅ Pass | ⏳ Partial/Scaffolded | ❌ Not Started |
|---------|-----------|--------|----------------------|----------------|
| 1 — File Upload | 7 | 7 | 0 | 0 |
| 2 — Comparison Agent | 3 | 3 | 0 | 0 |
| 3 — Evidence-Backed Insights | 4 | 4 | 0 | 0 |
| 4 — Contract Identification | 2 | 2 | 0 | 0 |
| 5 — AiDa / Bedrock Onboarding | 5 | 1 | 1 | 3 |
| 6 — AD Groups | 2 | 0 | 0 | 2 |
| 7 — Logging & Monitoring | 3 | 0 | 0 | 3 |
| 8 — Architecture / ATX | 3 | 0 | 1 | 2 |
| 9 — AI Governance | 2 | 0 | 0 | 2 |
| 10 — Singlestore (D2) | 2 | 0 | 0 | 2 |
| **Total** | **33** | **17** | **2** | **14** |

**D1 functional ACs (Features 1–4): 16/16 PASS**  
**D1 infrastructure/governance ACs (Features 5–9): 1/15 PASS, 1 partial**  
**D2 ACs (Feature 10): 0/2**
