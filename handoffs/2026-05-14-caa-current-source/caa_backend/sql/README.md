# CAA SQL DDL — `caa_backend/sql/`

## Files

| File | Purpose |
|---|---|
| `create_tables.sql` | DDL for `CAA_ANALYSIS` and `CAA_BRONZE_CHUNK`, including upload `ANALYSIS_MODE` and `COMPARISON_CONTEXT_IDENTIFIER`. Hand-authored, idempotent in the AiDa sense (use the drop script first; SingleStore does not have universal `CREATE TABLE IF NOT EXISTS` for FK-bearing tables). |
| `alter_2026_05_doc_to_kb_mode.sql` | Backfill-safe migration that adds upload mode/context columns to an existing `CAA_ANALYSIS`. |
| `create_tables_kb.sql` | DDL for `CAA_KB_COLLECTION`, `CAA_KB_MEMBER`, and interim JSON-backed `CAA_KB_EMBEDDING`. Native vector column choice is still gated on Step 0 SingleStore evidence. |
| `drop_tables_kb.sql` | Drop script for KB tables in dependency order. |
| `drop_tables.sql` | Drop script with `SET FOREIGN_KEY_CHECKS = 0/1` toggle, mirroring `MUFG/aida/aid_aida-backend/sql_commands_overall/create_tables.py::drop_all_tables`. Lists tables in dependency order (child → parent). |

## How to apply

The DDL is **not auto-applied** at runtime. Apply via the AiDa `TableManager` pattern at `MUFG/aida/aid_aida-backend/sql_commands_overall/create_tables.py:25-51`:

1. Open a SingleStore connection using the same secrets path that `caa_backend/storage.py` uses (`/application/aid/{env}/caa-app-secret`).
2. Read the SQL script file content.
3. Statement-split on `;`.
4. Execute each statement under a single transaction; commit at end.
5. For drops, toggle `SET FOREIGN_KEY_CHECKS = 0; ...; SET FOREIGN_KEY_CHECKS = 1;` so child rows do not block parent drops.

Example (adapted from AiDa's `TableManager.create_tables`):

```python
from mysql.connector import connect

conn = connect(host=..., port=..., user=..., database=..., password=...)
cursor = conn.cursor()
with open("caa_backend/sql/create_tables.sql", "r") as f:
    statements = [s.strip() for s in f.read().split(";") if s.strip()]
for stmt in statements:
    cursor.execute(stmt)
conn.commit()
cursor.close()
conn.close()
```

## Namespace contract

Every table CAA owns is prefixed `CAA_*`. The current set:

- `CAA_ANALYSIS` — one row per uploaded contract, with `solo`, `one_to_one`, or `kb` mode.
- `CAA_BRONZE_CHUNK` — one row per text chunk (FK to `CAA_ANALYSIS`).
- `CAA_KB_COLLECTION` — KB membership grouping.
- `CAA_KB_MEMBER` — analysis-to-collection link.
- `CAA_KB_EMBEDDING` — embeddings for retrieval. This is currently JSON-backed until Step 0 confirms the exact SingleStore vector column shape.

## Forward compatibility notes

- `ANALYSIS_IDENTIFIER` is `VARCHAR(64)` — wide enough for UUID v4 hex (32 chars) plus future schemes (e.g., a `caa-` prefix or `caa-{env}-{uuid}` form). Do not narrow this column without a migration plan.
- `USER_IDENTIFIER` is `VARCHAR(64)` — matches AiDa's `REF_USER.UNIQUE_IDENTIFIER` shape so a future hardening pass can introduce a real FK.
- `SCHEMA_VERSION` lives on the row so v2 can carry both `contract_analyzer_bronze_v1` and `contract_analyzer_bronze_v2` records without a migration window.

## AiDa-convention adoption scope

Adopted columns: `EFFECTIVE_FROM_TIMESTAMP`, `ACTIVE_INDICATOR`, `As_of_Timestamp`.

Not adopted: `SOURCE_SYSTEM_IDENTIFIER`, `FILE_IDENTIFIER`, `BRANCH_SECTOR_IDENTIFIER`, `LAST_CHANGE_USER_IDENTIFIER`. Rationale: these are AiDa-platform lineage columns (single platform "AID", a single `TEST_AIDA` file id, an MUFG internal branch code, and a hard-coded `aid_del` bot identifier) and do not map onto CAA's per-user-uploaded-contract domain. See the DDL header comment block for the full rationale.

## See also

- Plan tree: `docs/week_7/05_08_2026/PLANS/caa-singlestore-bronze-migration/`
- Storage class implementing this schema: `caa_backend/storage.py` (Step 2)
- Updated storage policy doc: `contract-analyst-agent-mockup/backend_fastapi/STORAGE_POLICY.md` (Step 8)
- AiDa schema reference: `MUFG/aida/aid_aida-backend/history/singleStoreHistory.py` (TCOR_CHAT row shape)
- AiDa DDL execution reference: `MUFG/aida/aid_aida-backend/sql_commands_overall/create_tables.py`
