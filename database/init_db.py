#!/usr/bin/env python3
"""
Initialize PostgreSQL database with schema for session analysis system.

Usage:
    python3 .claude/scripts/init_db.py [--db-url postgresql://user:pass@localhost:5432/claude_sessions]

Environment Variables:
    DATABASE_URL - PostgreSQL connection string (overrides --db-url)
"""

import psycopg2
import argparse
import os
import sys
from pathlib import Path

# PostgreSQL schema with all 3 tables and indexes
SCHEMA_SQL = """
-- sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(36) PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    git_branch VARCHAR(255),
    task_description TEXT,
    agent_name VARCHAR(100),
    total_tokens_input INTEGER DEFAULT 0,
    total_tokens_output INTEGER DEFAULT 0,
    total_tokens_cache INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(10,6) DEFAULT 0.0,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    outcome VARCHAR(20) CHECK(outcome IN ('SUCCESS', 'PARTIAL', 'BLOCKED', 'FAILED')),
    cost_per_line NUMERIC(10,6),
    cost_efficiency_rating VARCHAR(20) CHECK(cost_efficiency_rating IN ('excellent', 'good', 'poor')),
    summary JSONB,
    needs_manual_review BOOLEAN DEFAULT FALSE,
    high_cost_alert BOOLEAN DEFAULT FALSE,
    pattern_alert BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_outcome ON sessions(outcome);
CREATE INDEX IF NOT EXISTS idx_sessions_git_branch ON sessions(git_branch);
CREATE INDEX IF NOT EXISTS idx_sessions_flags ON sessions(needs_manual_review, high_cost_alert, pattern_alert) WHERE (needs_manual_review OR high_cost_alert OR pattern_alert);
CREATE INDEX IF NOT EXISTS idx_sessions_summary_gin ON sessions USING GIN(summary);

-- tool_usage table
CREATE TABLE IF NOT EXISTS tool_usage (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    tool_params JSONB,
    timestamp TIMESTAMPTZ NOT NULL,
    duration_ms INTEGER,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error TEXT,
    output_summary TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tool_usage_session_id ON tool_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_usage_tool_name ON tool_usage(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_usage_timestamp ON tool_usage(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tool_usage_success ON tool_usage(success);
CREATE INDEX IF NOT EXISTS idx_tool_usage_params_gin ON tool_usage USING GIN(tool_params);

-- events table
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(50) NOT NULL CHECK(event_type IN (
        'tdd_block', 'hook_block', 'timeout', 'error', 'test_failure', 'validation_error'
    )),
    timestamp TIMESTAMPTZ NOT NULL,
    tool_name VARCHAR(100),
    error_message TEXT,
    severity VARCHAR(20) DEFAULT 'medium' CHECK(severity IN ('low', 'medium', 'high', 'critical')),
    context_data JSONB,
    resolved BOOLEAN DEFAULT FALSE,
    retry_count INTEGER DEFAULT 0,
    resolution_notes TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_tool_name ON events(tool_name);
CREATE INDEX IF NOT EXISTS idx_events_context_gin ON events USING GIN(context_data);
"""

def init_database(db_url: str):
    """Initialize PostgreSQL database with schema."""
    conn = None
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(db_url)
        conn.autocommit = True  # For CREATE INDEX IF NOT EXISTS
        cursor = conn.cursor()

        # Execute schema
        cursor.execute(SCHEMA_SQL)

        # Verify tables created
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        print(f"✅ Database initialized: {db_url.split('@')[1] if '@' in db_url else db_url}")
        print(f"📊 Tables created: {', '.join(tables)}")
        print(f"🔒 Features: JSONB, TIMESTAMPTZ, GIN indexes, CASCADE DELETE")

        cursor.close()
    except psycopg2.Error as e:
        print(f"❌ Database initialization failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize session analysis database (PostgreSQL)")
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL", "postgresql://localhost:5432/claude_sessions"),
        help="PostgreSQL connection string (default: $DATABASE_URL or postgresql://localhost:5432/claude_sessions)"
    )
    args = parser.parse_args()

    init_database(args.db_url)
