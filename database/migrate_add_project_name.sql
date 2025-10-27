-- PostgreSQL Migration: Add project_name column for multi-repository support
-- Run this ONCE before deploying hooks to multiple repositories
--
-- Usage:
--   psql -U your_user -d claude_sessions -f migrate_add_project_name.sql
--
-- Or from command line:
--   psql -U your_user -d claude_sessions -c "$(cat migrate_add_project_name.sql)"

BEGIN;

-- Add project_name column to sessions table
ALTER TABLE sessions
ADD COLUMN IF NOT EXISTS project_name VARCHAR(100);

-- Add project_name column to tool_usage table
ALTER TABLE tool_usage
ADD COLUMN IF NOT EXISTS project_name VARCHAR(100);

-- Add project_name column to events table
ALTER TABLE events
ADD COLUMN IF NOT EXISTS project_name VARCHAR(100);

-- Create indexes for faster project-based queries
CREATE INDEX IF NOT EXISTS idx_sessions_project_name ON sessions(project_name);
CREATE INDEX IF NOT EXISTS idx_tool_usage_project_name ON tool_usage(project_name);
CREATE INDEX IF NOT EXISTS idx_events_project_name ON events(project_name);

-- Optional: Set default project_name for existing records
-- UPDATE sessions SET project_name = 'N8N_dev' WHERE project_name IS NULL;
-- UPDATE tool_usage SET project_name = 'N8N_dev' WHERE project_name IS NULL;
-- UPDATE events SET project_name = 'N8N_dev' WHERE project_name IS NULL;

COMMIT;

-- Verify migration
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND column_name = 'project_name'
ORDER BY table_name;
