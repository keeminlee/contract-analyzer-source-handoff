# Root Backend FastAPI Return Surface

> **Role:** Prior MUFG-returned backend patch/evidence surface.

This directory is separate from both:

- `contract-analyst-agent-mockup/backend_fastapi/` — nested source-package backend.
- `caa_backend/` — current MUFG-side/live-style backend surface from the 05-08 SingleStore migration.

The root `backend_fastapi/main.py` came from earlier MUFG-side return/validation work. Preserve it for round-trip context, but do not assume it is the newest canonical backend over `caa_backend/`.

Packaging note: include it in broad handoff packets for context; call out explicitly if a packet is source-only and excludes this evidence surface.
