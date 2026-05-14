# Contract Analyst Agent

Deterministic contract analysis prototype for the HQ-side Contract Analyzer worktree.

Pipeline:

```text
Bronze -> Spine -> Dynamic Retrieval -> Router Decision -> DAG Steps -> Evidence Packet -> Answer
```

## Product Surface

- `agents/` - orchestrator plus overview and precision answer agents.
- `tools/` - extraction, spine construction, retrieval, classification, obligations, comparison, routing, and DAG helpers.
- `templates/` - document-type templates used by the deterministic pipeline.
- `precedent_store/` - baseline precedent data for comparison flows.
- `requirements.txt` - Python dependency baseline.

## What Was Removed From The Inbound Packet

The initial MUFG-side packet included unpack residue, generated demo reports, cached sample artifacts, presentation notes, and a transfer archive. Those were intentionally removed before Git tracking so this worktree starts from the product-bearing source surface.

## Quick Usage

Run the orchestrator against an input document:

```bash
python agents/orchestrator.py --doc path/to/contract.txt --mode auto --doc-type auto --query "summarize confidentiality"
```

Useful options:

- `--mode auto` lets the mock router pick overview or precision behavior.
- `--doc-type auto` lets the pipeline infer the document type.
- `--no-persist` runs without writing derived artifacts.

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## MUFG-Side Verification Handoff

If this source tree is received as a zip package, start with:

- `handoff/MUFG_SIDE_VERIFICATION.md` - MUFG-side validation commands, launch checks, and expected evidence.
- `handoff/PACKAGE_MANIFEST.md` - source zip include/exclude guidance.
- `handoff/EVIDENCE_RETURN_TEMPLATE.md` - template for returning command results, screenshots, blockers, and final recommendation.

## Notes

- Retrieval is intentionally minimal and deterministic.
- Router policy is currently regex-based mock logic.
- This repository is the first HQ-side implementation baseline for Contract Analyzer; future production work should preserve evidence-first behavior and avoid reintroducing generated packet artifacts as source.
