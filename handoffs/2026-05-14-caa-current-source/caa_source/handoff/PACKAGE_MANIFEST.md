# Package Manifest

> Provisional source-package manifest for MUFG-side Contract Analyzer verification.

---

## Package Identity

- Package name: `contract-analyzer-source-handoff`
- Source root after unzip: `contract-analyst-agent-mockup/`
- Current local validation commit at handoff-doc creation: `b71b65a`
- Verification guide: `handoff/MUFG_SIDE_VERIFICATION.md`
- Evidence template: `handoff/EVIDENCE_RETURN_TEMPLATE.md`

## Include In Source Zip

- `README.md`
- `requirements.txt`
- `.gitignore`
- `agents/`
- `backend_fastapi/`
- `frontend/`
- `handoff/`
- `precedent_store/`
- `templates/`
- `tools/`

## Exclude From Source Zip

- `.git/`
- `.venv/`
- `.pytest_cache/`
- `__pycache__/`
- `*.pyc`
- `backend_fastapi/runtime/`
- `frontend/node_modules/`
- `frontend/dist/`
- `frontend/test-results/`
- `frontend/tsconfig.tsbuildinfo`

## Preferred Zip Command

Run from the source root after all handoff docs are committed:

```powershell
git archive --format=zip --output ..\contract-analyzer-source-handoff-<commit>.zip HEAD
```

This produces a source-only package from tracked files and avoids dependency/build/runtime residue.

## Optional Separate Evidence Bundle

If review screenshots are needed in addition to source, attach the Starstory Step 8 artifacts separately:

- `docs/week_7/05_06_2026/PLANS/contract-analyzer-production-aida-agent/8_e2e-validation-and-handoff/artifacts/step8-golden-desktop.png`
- `docs/week_7/05_06_2026/PLANS/contract-analyzer-production-aida-agent/8_e2e-validation-and-handoff/artifacts/step8-golden-tablet.png`

The screenshots are not required in the source zip because `npm run screenshot` regenerates local UI evidence.

