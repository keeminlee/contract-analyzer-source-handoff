# CAA doc-to-KB — Verification Packet Manifest (2026-05-08)

> Index of files in the HQ → MUFG verification packet for the doc-to-KB workstream's external-dependency verification (Step 0 of `caa-doc-to-kb-comparison` plan tree).

---

## Packet identifier

- **Name:** `CAA_kb_verification_request_2026-05-08`
- **Authored:** 2026-05-08 evening (HQ, OMC lane, executor agent)
- **Authored for:** `docs/week_7/05_08_2026/PLANS/caa-doc-to-kb-comparison/0_mufg-external-dependency-verification/`
- **Lane:** OMC (Claude Code runtime, OMC workflow layer)
- **Mirrors prior cycle:** `EVIDENCE_RETURN_TEMPLATE.md` (returned GREEN 2026-05-06, `CAA_mufg_return_2026-05-06.zip`)

---

## Files in this packet

| # | File | Role | Authored by | MUFG action |
|---|------|------|-------------|-------------|
| 1 | `CAA_KB_VERIFICATION_2026-05-08.md` | Verification instructions — what to install, what to run, what to capture | HQ | Read; follow |
| 2 | `CAA_KB_EVIDENCE_RETURN_TEMPLATE_2026-05-08.md` | Evidence return template — fill out and return as `CAA_KB_VERIFICATION_RETURN_2026-05-{DD}.md` | HQ | Fill in; rename; return |
| 3 | `CAA_KB_PACKAGE_MANIFEST_2026-05-08.md` (this file) | Manifest — what's in the packet | HQ | Reference |
| 4 | `caa_kb_smoke_test.py` | Smoke harness — runs items (a), (c), (d) end-to-end | HQ | Execute as instructed |

All four files live at `MUFG/contract-analyzer-agent/handoff/`.

---

## Verification scope

The packet asks the MUFG verifier to confirm four external dependencies the embedding + retrieval lane needs:

| Item | Class | Description |
|------|-------|-------------|
| (a) | **Blocking gate** | `bedrock:InvokeModel` IAM grant on `AIH_Operator_SBX` confirmed + smoke `embed([...])` succeeds |
| (b) | **Blocking gate** | MUFG SingleStore version supports needed vector ops (one of `DOT_PRODUCT` / `JSON_ARRAY_PACK` / native `VECTOR` column type) — confirmed by MUFG DBA |
| (c) | **Decision input** | Measured Bedrock embedding-call latency p50/p95 from CAA deploy env, against representative spine-doc-sized strings |
| (d) | **Decision input** | Measured Titan-v2 cost per 100 docs at per-document granularity (v1 choice) |

Step 0 closes GREEN if and only if (a) and (b) both PASS. (c) and (d) close as DONE regardless of the values themselves.

---

## How this packet flows

```
HQ authors packet (2026-05-08)
    │
    ├─> Bundles into next outgoing daily handoff zip
    │   (path: MUFG/packets/2026-05-{DD}/CAA_handoff_2026-05-{DD}.zip)
    │
    ▼
MUFG-side verifier receives zip
    │
    ├─> Reads CAA_KB_VERIFICATION_2026-05-08.md
    ├─> Confirms IAM grant + runs caa_kb_smoke_test.py --mode iam-smoke         (item a)
    ├─> Runs SQL smoke on SingleStore + DBA confirmation                        (item b)
    ├─> Runs caa_kb_smoke_test.py --mode latency-and-cost --n 50                (items c, d)
    ├─> Fills in CAA_KB_EVIDENCE_RETURN_TEMPLATE_2026-05-08.md
    ├─> Saves as CAA_KB_VERIFICATION_RETURN_2026-05-{DD}.md
    ├─> Bundles return doc + attachments into:
    │   MUFG/packets/2026-05-{DD}/CAA_kb_verification_return_2026-05-{DD}.zip
    │
    ▼
HQ receives return zip
    │
    ├─> Step 0 closeout written:
    │     - GREEN if (a) and (b) both PASS
    │     - YELLOW if one gate item PASS, one FAIL
    │     - BLOCKED if both FAIL or item (b) is "neither path supported"
    │
    ├─> If GREEN: tree Steps 5-9 unblock; Steps 6/7 seed alert thresholds
    │             from items (c) and (d) measured values
    │
    └─> If YELLOW/BLOCKED: tree pauses; failure mode named; re-verification
                            on next packet cycle
```

---

## Plan tree state after packet authoring (2026-05-08)

| Step | Status |
|------|--------|
| 0 | `IN_PROGRESS` — packet authored; awaiting MUFG-side evidence return |
| 1 | `NOT_STARTED` — may begin under verification in flight per plan tree preconditions |
| 2 | `NOT_STARTED` — depends on 1 |
| 3 | `NOT_STARTED` — depends on 2 + sibling singlestore tree Step 1 (COMPLETE) |
| 4 | `NOT_STARTED` — depends on 3 |
| 5-9 | `NOT_STARTED` — **hard-gated on Step 0 GREEN** |
| 10-13 | `NOT_STARTED` — depend on 9 |

---

## Provenance

- Authored by: `oh-my-claudecode:executor` agent
- Session: 2026-05-08 evening, invocation `a5a55bfcd67bf1cad`
- Lane: OMC (Claude Code runtime, OMC workflow layer)
- Greenlight: YES — RALPLAN consensus pass approved 2026-05-08 (see plan root `## Provenance`)
