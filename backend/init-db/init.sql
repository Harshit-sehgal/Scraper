-- =============================================================================
-- DataForge Scraper — PostgreSQL Initialization
-- =============================================================================
-- This runs on first container startup. Creates the base schema and any
-- required extensions. The app.postgres_repository module handles
-- its own migrations, so this only sets up the minimal foundation.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- IMPORTANT: The jobs/recycle_bin tables and schema_version are NOT created here.
-- They are auto-managed by PostgresJobRepository._ensure_schema() which runs
-- application-level migrations on first connection. This ensures the schema
-- stays in sync with the app code.
--
-- This init script only ensures PostgreSQL extensions and database-level
-- configuration exist so that the asyncpg pool connection succeeds on
-- first attempt without errors.
