-- ============================================================================
-- CAA bronze persistence schema (v1) — SingleStore-compatible DDL
-- ============================================================================
-- Namespace contract: every CAA table is `CAA_*`. Mirrors AiDa's `TCOR_*` /
-- `REF_*` prefix convention but with a CAA-owned prefix so ownership is
-- obvious to the platform team. New CAA tables (e.g. doc-to-KB:
-- `CAA_KB_COLLECTION`, `CAA_KB_MEMBER`, `CAA_KB_EMBEDDING`) MUST follow this
-- prefix; FK to `CAA_ANALYSIS.ANALYSIS_IDENTIFIER` for any per-document
-- derived data.
--
-- Column-naming convention adoption from AiDa (Locked Decision 4):
--  - CAA ADOPTS:   EFFECTIVE_FROM_TIMESTAMP, ACTIVE_INDICATOR (TINYINT),
--                  As_of_Timestamp.
--  - CAA does NOT adopt: SOURCE_SYSTEM_IDENTIFIER, FILE_IDENTIFIER,
--                  BRANCH_SECTOR_IDENTIFIER, LAST_CHANGE_USER_IDENTIFIER.
--    Rationale: these are AiDa-platform lineage columns (single SOURCE_SYSTEM
--    of "AID", a single platform-wide FILE_IDENTIFIER, an MUFG-internal
--    branch/sector code, and a hard-coded "aid_del" bot identifier). They do
--    not map onto CAA's domain (a per-user-uploaded contract is not part of
--    AiDa's reference-data lineage).
--
-- Per-user ACL posture (Locked Decision 3):
--  - `USER_IDENTIFIER` carries the Azure AD `pid` claim.
--  - SOFT FK only — application code (`claims["pid"] == row.USER_IDENTIFIER`)
--    is the enforcement surface. No DB-level FK to `REF_USER` because CAA may
--    not have AiDa's `REF_USER` populated in all environments.
--  - The `USER_IDENTIFIER` column comment below documents the intended
--    binding for future hardening.
--
-- Forward compatibility with doc-to-KB:
--  - `CAA_ANALYSIS.ANALYSIS_IDENTIFIER` is the FK target for the future
--    `CAA_KB_COLLECTION` / `CAA_KB_MEMBER` / `CAA_KB_EMBEDDING` tables (see
--    `docs/week_7/05_08_2026/artifacts/contract-analyzer-doc-to-kb-comparison.md`
--    §4.3). PK type and length (VARCHAR(64)) chosen to match.
--
-- Excluded from v1 (Locked Decision 1):
--  - `tables[]` and `metadata` from the bronze payload. Both are passthrough
--    surfaces consumed in-process by the spine builder; persisting them would
--    lock the schema to AiDa-uninvolved structures. If v2 needs them, add a
--    sibling table or JSON column.
-- ============================================================================


-- Per-analysis row: one per uploaded contract.
CREATE TABLE CAA_ANALYSIS (
    ANALYSIS_IDENTIFIER             VARCHAR(64)     NOT NULL,
    USER_IDENTIFIER                 VARCHAR(64)     NOT NULL,
    ANALYSIS_MODE                   VARCHAR(16)     NOT NULL DEFAULT 'solo',
    COMPARISON_CONTEXT_IDENTIFIER   VARCHAR(64)     NULL,
    SOURCE_FILENAME                 VARCHAR(512)    NULL,
    SOURCE_EXTENSION                VARCHAR(16)     NULL,
    SOURCE_MIME_TYPE                VARCHAR(128)    NULL,
    SOURCE_SIZE_BYTES               BIGINT          NULL,
    EXTRACTED_TEXT                  LONGTEXT        NULL,
    EXTRACTED_TEXT_CHAR_COUNT       INT             NULL,
    SCHEMA_VERSION                  VARCHAR(64)     NOT NULL,
    EFFECTIVE_FROM_TIMESTAMP        DATETIME        NOT NULL,
    ACTIVE_INDICATOR                TINYINT         NOT NULL DEFAULT 1,
    As_of_Timestamp                 DATETIME        NOT NULL,
    PRIMARY KEY (ANALYSIS_IDENTIFIER),
    CHECK (ANALYSIS_MODE IN ('solo', 'one_to_one', 'kb')),
    INDEX IDX_CAA_ANALYSIS_USER_ACTIVE (USER_IDENTIFIER, ACTIVE_INDICATOR),
    INDEX IDX_CAA_ANALYSIS_MODE_CONTEXT (ANALYSIS_MODE, COMPARISON_CONTEXT_IDENTIFIER),
    INDEX IDX_CAA_ANALYSIS_EFFECTIVE_FROM (EFFECTIVE_FROM_TIMESTAMP)
);

-- Column comments (SingleStore supports COMMENT clauses in CREATE TABLE; some
-- versions require ALTER TABLE ... MODIFY for inline comments. Documented here
-- in DDL header for portability.)
--
-- ANALYSIS_IDENTIFIER  : VARCHAR(64) — UUID v4 hex (32 chars), server-assigned.
--                        Replaces SHA-of-content scheme; eliminates cross-user
--                        collisions (Locked Decision 2).
-- USER_IDENTIFIER      : VARCHAR(64) — Azure AD `pid` claim. SOFT FK to
--                        `REF_USER.UNIQUE_IDENTIFIER` (not enforced at DB
--                        layer; ACL is application-level — Locked Decision 3).
-- ANALYSIS_MODE        : VARCHAR(16) — upload mode: solo, one_to_one, or kb.
-- COMPARISON_CONTEXT_IDENTIFIER : VARCHAR(64) — baseline analysis id for
--                        one_to_one mode or KB collection id for kb mode.
-- SCHEMA_VERSION       : VARCHAR(64) — `contract_analyzer_bronze_v1` for v1
--                        rows. Allows online schema evolution.
-- EFFECTIVE_FROM_TIMESTAMP : DATETIME — when the row became effective.
-- ACTIVE_INDICATOR     : TINYINT (0/1) — soft-delete flag. Reads filter on
--                        `ACTIVE_INDICATOR = 1`.
-- As_of_Timestamp      : DATETIME — when the row was last touched.


-- Per-chunk row: one per chunk produced by `build_text_chunks`.
CREATE TABLE CAA_BRONZE_CHUNK (
    CHUNK_IDENTIFIER                VARCHAR(96)     NOT NULL,
    ANALYSIS_IDENTIFIER             VARCHAR(64)     NOT NULL,
    CHUNK_INDEX                     INT             NOT NULL,
    CHUNK_TEXT                      LONGTEXT        NOT NULL,
    SPAN_START                      INT             NOT NULL,
    SPAN_END                        INT             NOT NULL,
    EFFECTIVE_FROM_TIMESTAMP        DATETIME        NOT NULL,
    ACTIVE_INDICATOR                TINYINT         NOT NULL DEFAULT 1,
    PRIMARY KEY (CHUNK_IDENTIFIER),
    UNIQUE KEY UQ_CAA_BRONZE_CHUNK_INDEX (ANALYSIS_IDENTIFIER, CHUNK_INDEX),
    CONSTRAINT FK_CAA_BRONZE_CHUNK_ANALYSIS
        FOREIGN KEY (ANALYSIS_IDENTIFIER)
        REFERENCES CAA_ANALYSIS (ANALYSIS_IDENTIFIER)
);

-- CHUNK_IDENTIFIER  : VARCHAR(96) — composed of `{ANALYSIS_IDENTIFIER}__{chunk_index}`
--                     for determinism. 64 (analysis) + 2 (separator) + 30 (room for index)
--                     fits in 96 with comfortable headroom.
-- CHUNK_INDEX       : INT — 0-based ordinal. UNIQUE per analysis.
-- CHUNK_TEXT        : LONGTEXT — raw chunk text. Cap matches AiDa's persistence.
-- SPAN_START / SPAN_END : INT — character spans into CAA_ANALYSIS.EXTRACTED_TEXT.

-- Notes:
--   1. v1 does NOT cascade-soft-delete on chunks. When CAA_ANALYSIS.ACTIVE_INDICATOR
--      flips to 0, application reads filter on the parent row's flag, so chunks
--      become unreachable without a separate flag flip. Cascade is deferred to v2.
--   2. v1 does NOT persist `tables[]` or `metadata` from the bronze payload
--      (Locked Decision 1).
--   3. `EXTRACTED_TEXT` lives on CAA_ANALYSIS as a LONGTEXT column (not in a
--      separate CAA_BRONZE_FULLTEXT table). LONGTEXT cap (4 GB) vs upload cap
--      (10 MiB) gives ~400× headroom.
