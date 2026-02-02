-- Remove legacy/unused tables. Run once after deploying the schema cleanup.
-- SQLite & PostgreSQL compatible.

DROP TABLE IF EXISTS transcript_words;
DROP TABLE IF EXISTS transcript_segments;
DROP TABLE IF EXISTS results;
