-- Runs automatically the FIRST time the Postgres container starts (empty data volume).
-- To re-run it: docker compose down -v && docker compose up -d   (this wipes all data)

CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector: embeddings for glossary search (Phase 1)
