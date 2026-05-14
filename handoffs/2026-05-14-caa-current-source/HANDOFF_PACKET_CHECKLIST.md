# CAA Handoff Packet Checklist

> **Scope:** `MUFG/contract-analyzer-agent/`
> **Purpose:** Prevent incomplete CAA zips by making the active source surfaces explicit.
> **Authority:** Navigational only. Plan roots, closeouts, and MUFG-side evidence remain authoritative.

## Grounding Reads

Read these before packaging or interpreting current CAA state:

1. `docs/week_7/05_08_2026/PLANS/INDEX.md`
2. `docs/week_7/05_08_2026/PLANS/caa-aida-style-logging-adoption/10_coherence-verification-pass/COHERENCE_REPORT.md`
3. `docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/9_coherence-verification-pass/COHERENCE_VERIFICATION_REPORT.md`
4. `docs/week_8/05_11_2026/PLANS/caa-doc-to-kb-comparison/0_mufg-external-dependency-verification/PROGRESS.md`
5. `docs/week_7/05_08_2026/artifacts/contract-analyzer-doc-to-kb-comparison.md`

## Surfaces To Check

| Surface | What to check | Why |
|---|---|---|
| `contract-analyst-agent-mockup/` | `git status --short`; tracked + untracked source/test/policy files | Nested source package; easy to over-focus here and miss siblings. |
| `caa_backend/` | `main.py`, `storage.py`, `sql/`, `tests/`, `MIGRATION_NOTES.md` | 05-08 SingleStore migration and live-style backend surface. |
| `aida_backend/` | `page_operations.py` | AiDa compatibility/marketplace integration context. |
| `backend_fastapi/` | Root-level `main.py` | Prior MUFG-returned patch surface; preserve for round-trip context. |
| `handoff/` | Request docs, return templates, compatibility notes | Instructions and evidence-return contract. |
| `screenshots/` | UI proof images | Useful for product/UI validation packets. |

## Current Doc-To-KB Verification Packet

For the 2026-05-11 outbound KB verification request, the zip should include:

- `CAA_KB_VERIFICATION_2026-05-08.md`
- `CAA_KB_EVIDENCE_RETURN_TEMPLATE_2026-05-08.md`
- `CAA_KB_PACKAGE_MANIFEST_2026-05-08.md`
- `caa_kb_smoke_test.py`
- `caa_source/` from `contract-analyst-agent-mockup/`
- `caa_backend/`
- `aida_backend/`
- `backend_fastapi/`
- `handoff/`
- `screenshots/`

Exclude generated caches and dependency directories:

- `.git/`
- `__pycache__/`
- `.pytest_cache/`
- `.venv/`
- `node_modules/`
- `dist/`
- `test-results/`
- `backend_fastapi/runtime/`

## Verification

After building the zip, inspect it:

```powershell
tar -tf MUFG/packets/05_11_2026/CAA_kb_verification_request_2026-05-11.zip |
  Select-String -Pattern 'caa_backend/main.py|caa_backend/storage.py|aida_backend/page_operations.py|caa_source/backend_fastapi/main.py|CAA_KB_VERIFICATION'
```

The output must show every major surface above before pushing to the GitHub handoff repo.
