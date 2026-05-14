-- ============================================================================
-- CAA doc-to-KB Step 2 migration: upload mode + comparison context
-- ============================================================================
-- Backfill-safe for existing rows: historical uploads become `solo`.

ALTER TABLE CAA_ANALYSIS
    ADD COLUMN ANALYSIS_MODE VARCHAR(16) NOT NULL DEFAULT 'solo',
    ADD COLUMN COMPARISON_CONTEXT_IDENTIFIER VARCHAR(64) NULL;

CREATE INDEX IDX_CAA_ANALYSIS_MODE_CONTEXT
    ON CAA_ANALYSIS (ANALYSIS_MODE, COMPARISON_CONTEXT_IDENTIFIER);

