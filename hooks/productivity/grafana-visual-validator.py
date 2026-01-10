#!/usr/bin/env python3
"""
Grafana Visual Validator Hook

Triggers automatically after Write/Edit on monitoring/grafana/dashboards/*.json
Spawns grafana-visual-validator agent to verify dashboard renders correctly.
"""

import json
import os
import sys


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Get file path from tool input
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Only trigger for Grafana dashboard files
    if "grafana/dashboards" not in file_path or not file_path.endswith(".json"):
        sys.exit(0)

    # Extract dashboard info
    dashboard_name = os.path.basename(file_path).replace(".json", "")

    # Output instruction to spawn validator agent
    output = {
        "decision": "allow",
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "spawnAgent": {
                "type": "grafana-visual-validator",
                "reason": f"Grafana dashboard '{dashboard_name}' was modified",
                "params": {
                    "dashboard_file": file_path,
                    "dashboard_name": dashboard_name,
                    "auto_fix": True,
                },
            },
            "message": f"[grafana-hook] Dashboard '{dashboard_name}' modified. Visual validation recommended.",
        },
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
