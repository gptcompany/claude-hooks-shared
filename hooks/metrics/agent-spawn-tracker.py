#!/usr/bin/env python3
"""
PreToolUse Hook: Agent Spawn Tracker

Intercepts Task tool calls to log which agents are spawned.
This is the KISS solution since Claude Code doesn't expose per-agent token usage.

Logs to: .claude/stats/agent_spawns.jsonl
"""

import json
import sys
from datetime import datetime
from pathlib import Path

STATS_DIR = Path.cwd() / ".claude" / "stats"
AGENT_SPAWNS_LOG = STATS_DIR / "agent_spawns.jsonl"


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Only intercept Task tool calls
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Task":
        print(json.dumps({}))
        sys.exit(0)

    # Extract agent info from tool input
    tool_input = input_data.get("tool_input", {})

    # Handle various input formats (string, dict, None, list)
    if tool_input is None:
        tool_input = {}
    elif isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            tool_input = {}
    elif not isinstance(tool_input, dict):
        # Handle unexpected types (list, int, etc.)
        tool_input = {}

    subagent_type = tool_input.get("subagent_type", "unknown")
    description = tool_input.get("description", "")
    prompt_preview = tool_input.get("prompt", "")[:200]  # First 200 chars

    # Log the spawn
    STATS_DIR.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "agent_spawn",
        "agent_type": subagent_type,
        "description": description,
        "prompt_preview": prompt_preview,
        "session_id": input_data.get("session_id", "unknown"),
    }

    with open(AGENT_SPAWNS_LOG, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Don't block - just log and continue
    print(json.dumps({}))
    sys.exit(0)


if __name__ == "__main__":
    main()
