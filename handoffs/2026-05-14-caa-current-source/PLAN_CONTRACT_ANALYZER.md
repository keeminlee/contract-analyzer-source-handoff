# Contract Analyzer Agent — Top-Level Implementation Plan

**Status:** Planning  
**Date:** 2026-05-04  
**ADO Epic:** DSE1-449  
**Owner:** Keemin / Sehaj  
**Release:** 3 — New Agents: Contract Analyzer  
**Canonical Mockup:** `Contracts/contract-analyst-agent-mockup/`  
**Purpose:** Defines the full scope of work to evolve the Contract Analyzer from deterministic mockup to production AiDa agent.

---

## Locked Decisions (Do Not Re-Litigate)

- **Document ingestion model:** BYO Documents via file upload — users upload their own contracts. No FileNet/Y71 dependency. Runs independently from Asset Locator.
- **Contract corpus:** Open / contract-type-agnostic. The spine builder must generalize to any contract type, not just NDA/Credit/Loan/MSA. Doc type is inferred, not pre-selected.
- **Virus scanning:** Not required for v1.
- **Rendering target:** Dashboard + chat UI, closely modeled on Epiphany/Banker360. Evidence-backed answers surfaced in a React frontend with a persistent chat panel. Not a downloadable report.
- **Infrastructure:** Standalone — does not share ingestion pipeline with Asset Locator in v1.

---

## What Is Already Built (Mockup — Do Not Rebuild)

- **Bronze → Silver pipeline**: `bronze_extractor`, `spine_builder`, `auto_spine_builder`, `spine_resolver`, `dynamic_chunker` — structural parsing from raw contract text
- **DAG task runner**: `tools/dag_runner.py` with YAML templates for NDA, Credit Agreement, Loan Agreement, MSA
- **Agent modes**: `overview_agent.py` (summary path), `precision_agent.py` (citation-backed path)
- **Orchestrator**: `agents/orchestrator.py` + heuristic router `tools/mock_router.py`
- **Risk layer**: `clause_classifier.py`, `obligation_extractor.py`, `playbook_compare.py`
- **Precedent baselines**: JSON baselines for all 4 doc types in `precedent_store/`
- **Demo surface**: evidence packets, HTML reports, sample docs (NDA + Credit Agreement)

---

## What Needs To Be Built (Backlog → Production)

| # | Feature | Backlog Item | Estimate |
|---|---|---|---|
| 1 | **File Upload & Ingestion** | User uploads contract (PDF/DOCX); dynamic bronze extraction + agnostic spine build | 1 Sprint |
| 2 | **LLM Integration** | Replace mock LLM with real Bedrock via OAuth/API GW proxy (`LLMGenerate` pattern) | 1 Sprint |
| 3 | **Comparison Agent** | Semantic diff of uploaded doc vs. prior/standard agreement (user-supplied or precedent store) | 1 Sprint |
| 4 | **Evidence-Backed Insights** | LLM-driven obligation extraction, risk flagging, citation output (precision mode) | 1 Sprint |
| 5 | **Dashboard + Chat UI** | Epiphany-style React frontend — contract summary dashboard + persistent chat panel | TBD |
| 6 | **FastAPI Backend** | API layer wrapping pipeline; reference: `Banker360_Epiphany/backend_fastapi/` | TBD |
| 7 | **AiDa Marketplace Onboarding** | Agent manifest, marketplace registration, routing wired into AiDa | TBD |

---

## Key Gaps vs. Mockup

| Area | Mockup State | Production Gap |
|---|---|---|
| LLM calls | Deterministic / rule-based (mocked) | Real Bedrock calls via OAuth/proxy (`LLMGenerate` pattern from `aid_aida-backend`) |
| Spine builder | Typed to 4 doc types (NDA/Credit/Loan/MSA) | Must be generalized — infer contract type, not assume it |
| Retrieval | Naive top-k chunk ranking | Semantic retrieval; may need vector store |
| Router | Heuristic / keyword | Semantic routing that generalizes to real-world query variance |
| Comparison | Rule-based playbook diff | True semantic diff; baseline can be user-uploaded or precedent store |
| Document source | Static sample files | User file upload (PDF/DOCX) → dynamic bronze extraction |
| Frontend | Static HTML reports | Epiphany-style React dashboard + chat panel |
| API layer | None | FastAPI wrapper (reference: `Banker360_Epiphany/backend_fastapi/`) |
| AiDa integration | None | Agent manifest, marketplace registration, AiDa routing |

---

## Key Dependencies

- **Bedrock / LLM proxy**: OAuth2 + API Gateway proxy — reuse `LLMGenerate` pattern from `AiDa/AiDa-ADO/aid_aida-backend/Bedrock_calls/llm_gen.py`; SSO profile `keemin` (AID_Operator_DEV) for local dev
- **Banker360 FastAPI**: `Banker360_Epiphany/backend_fastapi/` is the reference implementation for evidence packet builder, API contracts pattern, and FastAPI structure
- **Epiphany Frontend**: `Banker360_Epiphany/frontend/` is the reference for the React dashboard + chat UI target
- **AiDa agent onboarding pattern**: Must align with how other agents are registered in `AiDa/AiDa-ADO/aid_aida-backend` marketplace

---

## Open Questions (Planning Not Finalized)

- [ ] What is the authoritative source for "prior agreements" for comparison — user uploads a second document, or we maintain a precedent store, or both?
- [ ] File upload size/format constraints — PDF only or DOCX too? Max size?
- [ ] Does the AiDa marketplace UI need any changes to support file upload (vs. text-only chat agents)?
- [ ] Which Claude model via the AiDa API GW proxy — Haiku for speed or Sonnet/Opus for precision?

---

## Steps (To Be Broken Down)

| # | Directory | Step | Status |
|---|---|---|---|
| 1 | `1_upload-ingestion/` | File upload endpoint + dynamic bronze extraction + agnostic spine builder | Not Started |
| 2 | `2_llm-integration/` | Wire real `LLMGenerate` (OAuth→API GW→Bedrock); lift orchestrator to production | Not Started |
| 3 | `3_comparison-agent/` | Semantic comparison engine — uploaded doc vs. prior/baseline | Not Started |
| 4 | `4_evidence-insights/` | LLM-backed obligation extraction, risk flagging, citation output (precision mode) | Not Started |
| 5 | `5_api-layer/` | FastAPI backend — file upload, pipeline orchestration, chat endpoint | Not Started |
| 6 | `6_frontend/` | Epiphany-style React dashboard + chat panel | Not Started |
| 7 | `7_aida-onboarding/` | Agent manifest, marketplace registration, routing wired into AiDa | Not Started |

---

## Reference Files

- Mockup root: `Contracts/contract-analyst-agent-mockup/`
- System prompt / policy: `Contracts/Prompt.txt`
- Flow diagram: `Contracts/Conracts_Analyst_Agent_Diagram.drawio`
- Product narrative: `Contracts/contract-analyst-agent-mockup/Presentation_3_5.md`
- UI copy: `Contracts/contract-analyst-agent-mockup/Mock UI Microcopy.md`
- Math/design doc: `Contracts/CAA-mockup-V2/GCIB_Contract_Analyst_Agent_Math.pdf`
- FastAPI reference: `Banker360_Epiphany/backend_fastapi/`
- Frontend reference: `Banker360_Epiphany/frontend/`
- LLM proxy pattern: `AiDa/AiDa-ADO/aid_aida-backend/Bedrock_calls/llm_gen.py`
- AiDa v2 arch notes: `PLANS/aida-v2/PLAN_AIDA_V2.md`
