-- Drop script for CAA bronze persistence (mirrors AiDa's
-- `TableManager.drop_all_tables` toggle pattern). Tables listed in dependency
-- order: child (CAA_BRONZE_CHUNK) before parent (CAA_ANALYSIS).

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS CAA_BRONZE_CHUNK;
DROP TABLE IF EXISTS CAA_ANALYSIS;

SET FOREIGN_KEY_CHECKS = 1;
