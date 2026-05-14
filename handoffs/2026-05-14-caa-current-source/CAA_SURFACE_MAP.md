# Contract Analyzer Agent — Surface Map

> **Subproject:** Contract Analyzer Agent
> **Status:** Active HQ/MUFG handoff and implementation surface.
> **Purpose:** Keep the CAA product source, MUFG-returned integration surfaces, verification packets, screenshots, and follow-up backlog legible from one directory.

## Current State

CAA has multiple active source surfaces. Do not assume `contract-analyst-agent-mockup/` is the whole handoff.

The 2026-05-08 Gold plan evidence is the current grounding layer:

- `docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/` — COMPLETE GREEN; logging, audit lines, auth-claim threading, privacy tests, and `LOGGING_POLICY.md`.
- `docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/` — COMPLETE GREEN; CAA bronze persistence moved to SingleStore-style `caa_backend/` storage with UUID ids, `USER_IDENTIFIER` ACL, soft-delete, and 110/110 tests.
- `docs/week_8/05_11_2026/PLANS/caa-doc-to-kb-comparison/` — current forward feature; Step 0 `IN_PROGRESS`, waiting for MUFG-side Bedrock/SingleStore vector evidence return.
- `docs/week_8/05_14_2026/artifacts/CAA_layer3_2026-05-14/` — MUFG-side Layer 3 inbound packet imported into `contract-analyst-agent-mockup/`; live insights/chat routes and source/PDF citation viewer refreshed, with local backend 110/110, Python compile, frontend 6/6, and frontend build passing after adding the local raw-upload storage seam to `caa_backend/storage.py`.

## Directory Roles

| Path | Role | Include in handoff? |
|---|---|---|
| `contract-analyst-agent-mockup/` | Nested git/source package for the product mockup, frontend, tools, tests, and policy docs. | Yes, as `caa_source/` when sending a source snapshot. |
| `caa_backend/` | MUFG-side/live-style CAA backend surface from 05-08 plans: SingleStore storage, ACL, soft-delete, DDL, and tests. | Yes, when sending current CAA backend changes. |
| `aida_backend/` | AiDa-side compatibility surface touched by CAA marketplace/launch work. | Yes, when the packet is meant to preserve latest AiDa compatibility context. |
| `backend_fastapi/` | Older/root-level returned backend patch surface from prior MUFG verification. Preserve as evidence/reference. | Usually yes for round-trip context; do not treat as canonical over `caa_backend/`. |
| `handoff/` | Outbound and inbound verification docs/templates. | Yes for any MUFG-side request or return packet. |
| `screenshots/` | Visual evidence from CAA validation. | Include when asking for product/UI validation or preserving proof. |
| `backlog/` | CAA follow-up queue. | Reference, not usually bundled unless requested. |

## Packet Rule

Before pushing a CAA zip, inspect all of these surfaces:

```powershell
git -C MUFG/contract-analyzer-agent/contract-analyst-agent-mockup status --short
Get-ChildItem MUFG/contract-analyzer-agent/caa_backend -Recurse -File
Get-ChildItem MUFG/contract-analyzer-agent/aida_backend -Recurse -File
Get-ChildItem MUFG/contract-analyzer-agent/backend_fastapi -Recurse -File
Get-ChildItem MUFG/contract-analyzer-agent/handoff -File
```

If the packet is for the current doc-to-KB verification gate, include the four `CAA_KB_*` handoff files plus the relevant current CAA source surfaces. The MUFG-side return should come back as a filled evidence template plus attachments in a `CAA_kb_verification_return_*.zip`.
