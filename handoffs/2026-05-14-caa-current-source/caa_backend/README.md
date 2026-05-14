# CAA Backend Surface

> **Role:** MUFG-side/live-style CAA backend surface.
> **Grounding plan:** `docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/`

This directory is not a cache and not a duplicate to ignore. It is the surface where the 2026-05-08 SingleStore bronze migration landed.

Key files:

- `main.py` — live-style API entrypoint with UUID analysis ids, auth claim threading, owner-only reads, and soft-delete route.
- `storage.py` — `BronzeStore` with AiDa-style `_load_secrets -> _get_connection -> close`, `CAA_STORAGE_BACKEND`, and in-memory test seam.
- `sql/` — `CAA_ANALYSIS` / `CAA_BRONZE_CHUNK` DDL and teardown helpers.
- `tests/` — MUFG-style backend tests and optional SingleStore smoke harness.
- `MIGRATION_NOTES.md` — local-filesystem-to-SingleStore migration rationale and discarded legacy `runtime/bronze/` posture.

Packaging note: include this directory in CAA handoff zips whenever the packet claims to include the current backend/storage state.
