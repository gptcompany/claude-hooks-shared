#!/usr/bin/env python3
"""
CI Batch Check Hook - Warns about multiple pushes in short timeframe.

FAANG best practice: 1 logical unit = 1 push
Prevents CI queue explosion from incremental fixes.
"""

import json
import sys
import time
from pathlib import Path

# Config
PUSH_COOLDOWN_MINUTES = 10
PUSH_HISTORY_FILE = Path("/tmp/claude_push_history.json")
MAX_RAPID_PUSHES = 2  # Warn after this many pushes within cooldown


def load_push_history() -> list:
    """Load push timestamps from history file."""
    if PUSH_HISTORY_FILE.exists():
        try:
            with open(PUSH_HISTORY_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_push_history(history: list) -> None:
    """Save push timestamps to history file."""
    # Keep only last hour of history
    cutoff = time.time() - 3600
    history = [ts for ts in history if ts > cutoff]
    with open(PUSH_HISTORY_FILE, "w") as f:
        json.dump(history, f)


def get_recent_pushes(history: list, minutes: int) -> int:
    """Count pushes within the last N minutes."""
    cutoff = time.time() - (minutes * 60)
    return sum(1 for ts in history if ts > cutoff)


def main():
    # Read hook input
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only check git push commands
    if "git push" not in command and "git push" not in command.replace("&&", " "):
        sys.exit(0)

    # Load history
    history = load_push_history()
    recent_count = get_recent_pushes(history, PUSH_COOLDOWN_MINUTES)

    # Record this push attempt
    history.append(time.time())
    save_push_history(history)

    # Check if too many rapid pushes
    if recent_count >= MAX_RAPID_PUSHES:
        # Output warning but don't block
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "suppressToolUse": False,
                "message": f"[CI Batch Warning] {recent_count + 1} pushes in {PUSH_COOLDOWN_MINUTES}min. "
                f"Consider batching fixes into 1 logical unit per push (FAANG best practice).",
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
