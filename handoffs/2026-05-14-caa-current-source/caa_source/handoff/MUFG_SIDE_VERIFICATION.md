# MUFG-Side Verification Guide

> Provisional handoff artifact for the Contract Analyzer source package.
> Audience: MUFG-side agent or engineer validating the source after unzip.
> Source root: `contract-analyst-agent-mockup/`

---

## Goal

Verify the Contract Analyzer package in the MUFG-side environment and return evidence on three questions:

1. Does the Contract Analyzer source package install and pass local product validation?
2. Can the live product expose and serve the expected upload, insights, and chat contracts in the target MUFG environment?
3. Can AiDa marketplace launch the Contract Analyzer route from the enterprise marketplace surface?

Local pre-send validation already proved the internal pipeline and UI rendering with fake/mocked external boundaries. MUFG-side validation is still needed for enterprise environment dependencies, AiDa launch, and any live endpoint bridge work completed before send.

---

## Package Contents To Expect

The source zip should contain the tracked source tree, including:

- `backend_fastapi/` - FastAPI upload service and backend tests.
- `agents/` - deterministic orchestrator and answer agents.
- `tools/` - extraction, spine, retrieval, routing, proxy contract, insight packet, and comparison helpers.
- `frontend/` - AiDa-styled React/Vite frontend and Playwright tests.
- `templates/` and `precedent_store/` - deterministic reference assets.
- `handoff/` - this verification guide, package manifest, and evidence return template.

The source zip should not include generated dependency/build/runtime folders such as `.git/`, `.venv/`, `frontend/node_modules/`, `frontend/dist/`, `frontend/test-results/`, `backend_fastapi/runtime/`, or Python cache directories.

Preferred zip creation from the source repo is:

```powershell
git archive --format=zip --output ..\contract-analyzer-source-handoff-<commit>.zip HEAD
```

---

## Environment Setup

From the unzipped source root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cd frontend
npm ci
cd ..
```

If MUFG environment policy uses a managed Python/Node environment, use that environment instead and record the exact versions in `handoff/EVIDENCE_RETURN_TEMPLATE.md`.

---

## Product Validation Commands

Run from the source root unless noted.

```powershell
python -m unittest discover -s backend_fastapi/tests -v
python -m compileall agents tools backend_fastapi
```

Run from `frontend/`:

```powershell
npm test -- --run
npm run build
npm run screenshot
```

Expected local evidence:

- Backend tests pass, including `test_e2e_validation_contracts`.
- Frontend Vitest passes.
- Vite production build succeeds.
- Playwright writes screenshots under `frontend/test-results/`, including `step8-golden-desktop.png` and `step8-golden-tablet.png`.

---

## Contract Analyzer Live Endpoint Checks

If the source package includes the live analysis/chat endpoint bridge, verify these endpoints in the MUFG environment.

Expected endpoints:

- `GET /health`
- `POST /api/v1/uploads`
- `GET /api/v1/analyses/{analysis_id}/insights`
- `POST /api/v1/analyses/{analysis_id}/chat`

Suggested smoke sequence:

```powershell
# Start backend, adjust command/host/port to MUFG deployment pattern if needed.
uvicorn backend_fastapi.main:app --host 127.0.0.1 --port 8000
```

In a second shell:

```powershell
$contract = @"
CREDIT AGREEMENT

1 Interest
The Borrower shall pay interest at 9 percent per annum.

2 Event of Default
Failure to pay principal or interest when due is an Event of Default after a 30 day cure period.
"@
$tmp = New-TemporaryFile
Set-Content -LiteralPath $tmp -Value $contract -Encoding UTF8

$upload = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/uploads" -Form @{ file = Get-Item $tmp }
$analysisId = $upload.analysis_id

Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/analyses/$analysisId/insights"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/analyses/$analysisId/chat" -ContentType "application/json" -Body '{"message":"Where is default cited?"}'
```

Expected live endpoint evidence:

- Upload returns `schema_version: contract_analyzer_upload_v1`, `analysis_id`, `session_id`, and `bronze`.
- Insights returns `schema_version: contract_analyzer_insight_answer_packet_v1`, non-empty `findings`, non-empty `citations`, and cited `answer_text` or a structured low-evidence abstention.
- Chat returns `schema_version: contract_analyzer_grounded_answer_v1`, `answer_text` with citation ids, or a structured abstention/error state.

If `/insights` or `/chat` is missing, record this as the live endpoint bridge blocker. Do not treat frontend mocked Playwright success as live endpoint proof.

---

## AiDa Marketplace Verification

In the AiDa backend repo/environment, verify the marketplace manifest and launch path.

Focused manifest check:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest tests/test_contract_analyzer_marketplace.py -q
```

Expected manifest evidence:

- `ca-contract-analyzer-v1` is present exactly once.
- Agent name is `Contract Analyzer`.
- Status is `live`.
- Department is `GCIB`.
- `launch_url` points to the MUFG-side Contract Analyzer frontend URL.
- Upload metadata supports `.txt`, `.pdf`, `.docx`, max 25 MB, entrypoint `/api/v1/uploads`.

AiDa smoke anchors, if supported by the environment:

```powershell
$env:AIDA_PARALLEL_ENABLED='true'
python -m pytest poc/keemin_sse_observability_28_4/sse_smoke_test.py -s
python pocs/design5_smoke_test.py
```

Known pre-send blocker:

- These smoke anchors failed locally with `ModuleNotFoundError: No module named 'mysql'` from the AiDa retriever import path. If this still fails MUFG-side, record the dependency/import blocker and whether it is an environment issue or a smoke fixture issue.

---

## Browser Launch Verification

From AiDa marketplace:

1. Open the Agents/Marketplace surface.
2. Confirm the `Contract Analyzer` card appears under GCIB and is live.
3. Click the card launch/chat action.
4. Confirm the browser opens the Contract Analyzer frontend.
5. Upload a TXT/PDF/DOCX contract.
6. Confirm findings, evidence citations, and persistent chat render against the active `analysis_id`.

Evidence to capture:

- Screenshot of AiDa marketplace card.
- Screenshot after launch showing Contract Analyzer frontend URL.
- Screenshot after upload showing `analysis_id`, findings, citations, and chat answer citation.
- Network or console evidence for failed launch/API calls, if any.

---

## Evidence Return

Fill out `handoff/EVIDENCE_RETURN_TEMPLATE.md` and send it back with:

- Exact commit/package id.
- Environment versions.
- Command results.
- Screenshots or paths to screenshots.
- Any blocker stack traces.
- Decision recommendation: `GREEN`, `YELLOW`, or `BLOCKED`.

