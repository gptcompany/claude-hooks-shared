#!/usr/bin/env python3
"""
Tips Injector Hook (UserPromptSubmit)

Checks for tips from the previous session and offers to inject them.
Only triggers once per session, on the first user prompt.

Tips are saved by session-summary.py in ~/.claude/metrics/last_session_tips.json
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

TIPS_FILE = Path.home() / ".claude" / "metrics" / "last_session_tips.json"
INJECTED_MARKER = Path.home() / ".claude" / "metrics" / ".tips_injected"


def get_tips() -> dict:
    """Load tips from previous session."""
    if not TIPS_FILE.exists():
        return None

    try:
        with open(TIPS_FILE) as f:
            data = json.load(f)

        # Only use tips from last 24 hours
        timestamp = datetime.fromisoformat(data.get("timestamp", ""))
        if datetime.now() - timestamp > timedelta(hours=24):
            return None

        return data
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def was_already_injected(session_id: str) -> bool:
    """Check if tips were already injected this session."""
    if not INJECTED_MARKER.exists():
        return False

    try:
        marker = INJECTED_MARKER.read_text().strip()
        return marker == session_id
    except OSError:
        return False


def mark_injected(session_id: str):
    """Mark tips as injected for this session."""
    try:
        INJECTED_MARKER.parent.mkdir(parents=True, exist_ok=True)
        INJECTED_MARKER.write_text(session_id)
    except OSError:
        pass


def format_tips_compact(tips_data: dict) -> str:
    """Format tips in ultra-compact form for context."""
    tips = tips_data.get("tips", [])
    if not tips:
        return None

    # Only critical tips (priority 1)
    critical = [t["tip"].split(":")[0] for t in tips if t["priority"] == 1]
    if not critical:
        return None

    return f"[PREV SESSION TIPS] {' | '.join(critical[:2])}"


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    session_id = input_data.get("session_id", "unknown")

    # Only trigger once per session
    if was_already_injected(session_id):
        print(json.dumps({}))
        sys.exit(0)

    # Check for tips
    tips_data = get_tips()
    if not tips_data:
        print(json.dumps({}))
        sys.exit(0)

    # Format tips
    compact = format_tips_compact(tips_data)
    if not compact:
        mark_injected(session_id)
        print(json.dumps({}))
        sys.exit(0)

    # Mark as shown (don't show again this session)
    mark_injected(session_id)

    # Show notification and inject to context
    summary = tips_data.get("summary", {})
    notification = (
        f"Previous session: {summary.get('duration_min', 0):.0f}min, "
        f"{summary.get('tool_calls', 0)} calls, "
        f"{summary.get('errors', 0)} errors\n"
        f"Tips available: {len(tips_data.get('tips', []))}"
    )

    output = {
        "notification": notification,
        "message": compact  # Inject to context
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
