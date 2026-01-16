#!/usr/bin/env python3
"""
Session Insights Writer: SSOT Aggregator for session data.

This hook runs LAST among Stop hooks and aggregates data from:
- context-preservation.py → context_stats.json
- session-summary.py → last_session_tips.json
- session_analyzer.py → last_session_stats.json

Produces unified: session_insights.json

The SSOT is then read by session_start_tracker.py on next session start.
"""

import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path

# File paths
METRICS_DIR = Path.home() / ".claude" / "metrics"
CONTEXT_STATS_FILE = METRICS_DIR / "context_stats.json"
TIPS_FILE = METRICS_DIR / "last_session_tips.json"
STATS_FILE = METRICS_DIR / "last_session_stats.json"
INSIGHTS_FILE = METRICS_DIR / "session_insights.json"


def load_json_safe(path: Path) -> dict | None:
    """Load JSON file safely, return None on error."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
        session_id = input_data.get("session_id", "unknown")

        # Initialize insights structure
        insights = {
            "$schema": "session_insights_v1",
            "session_id": session_id,
            "ended_at": datetime.now().isoformat(),
        }

        # 1. Read context stats (from context-preservation.py)
        if context_data := load_json_safe(CONTEXT_STATS_FILE):
            insights["context"] = {
                "tokens_used": context_data.get("tokens_used", 0),
                "percentage": context_data.get("percentage", 0),
                "status": context_data.get("status", "normal"),
            }
            # Add delegation info if critical
            if context_data.get("suggested_agents"):
                insights["delegation"] = {
                    "recommended": True,
                    "agents": context_data["suggested_agents"],
                }
            # Cleanup temp file
            with contextlib.suppress(Exception):
                CONTEXT_STATS_FILE.unlink()

        # 2. Read tips (from session-summary.py)
        if tips_data := load_json_safe(TIPS_FILE):
            insights["tips"] = tips_data.get("tips", [])
            insights["analysis"] = tips_data.get("analysis", {})
            if summary := tips_data.get("summary"):
                insights["summary"] = {
                    "duration_min": summary.get("duration_min", 0),
                    "tool_calls": summary.get("tool_calls", 0),
                    "errors": summary.get("errors", 0),
                }

        # 3. Read git stats (from session_analyzer.py)
        if stats_data := load_json_safe(STATS_FILE):
            if git_data := stats_data.get("git"):
                insights["git"] = {
                    "uncommitted": git_data.get("has_changes", False),
                    "lines_added": git_data.get("lines_added", 0),
                    "lines_removed": git_data.get("lines_deleted", 0),
                    "files": {
                        "code": git_data.get("code_files", 0),
                        "test": git_data.get("test_files", 0),
                        "config": git_data.get("config_files", 0),
                    },
                }
            insights["commits"] = stats_data.get("commits", 0)

        # Ensure metrics directory exists
        METRICS_DIR.mkdir(parents=True, exist_ok=True)

        # Write unified SSOT
        INSIGHTS_FILE.write_text(json.dumps(insights, indent=2))

        # Output success (no systemMessage needed, this is just for aggregation)
        sys.exit(0)

    except Exception:
        # Fail silently - don't block on hook errors
        sys.exit(0)


if __name__ == "__main__":
    main()
