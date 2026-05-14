# CAA Handoff Directory

> **Role:** Outbound request docs, inbound evidence-return templates, compatibility notes, and smoke harnesses.

Important current files:

- `CAA_KB_VERIFICATION_2026-05-08.md` — instructions for MUFG-side KB dependency verification.
- `CAA_KB_EVIDENCE_RETURN_TEMPLATE_2026-05-08.md` — template MUFG-side fills and returns.
- `CAA_KB_PACKAGE_MANIFEST_2026-05-08.md` — manifest for the KB verification request.
- `caa_kb_smoke_test.py` — self-contained smoke harness for Bedrock IAM, latency, and cost checks.
- `EVIDENCE_RETURN_TEMPLATE.md` and `MUFG_SIDE_CHANGES.md` — prior source-handoff return shape and MUFG-side change record.
- `CAA_AIDA_COMPAT_2026-05-08.md` — AiDa compatibility note.

For the doc-to-KB Step 0 gate, this directory provides the request/return contract. The code/source surfaces live outside this directory and must be added to the zip separately when needed.
