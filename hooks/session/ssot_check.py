#!/usr/bin/env python3
"""
SSOT Check Hook - Verifies config drift on first message of session.

Runs once per session. If drift detected, warns user before proceeding.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Session flag - uses parent PID to track session
SESSION_FLAG = Path(tempfile.gettempdir()) / f".ssot_check_{os.getppid()}"


def main():
    # Skip if already ran this session
    if SESSION_FLAG.exists():
        print(json.dumps({"continue": True}))
        return 0

    # Mark as ran
    SESSION_FLAG.write_text("done")

    # Find project root (has config/canonical.yaml)
    cwd = Path.cwd()
    project_root = None
    for p in [cwd, *cwd.parents]:
        if (p / "config" / "canonical.yaml").exists():
            project_root = p
            break

    if not project_root:
        print(json.dumps({"continue": True}))
        return 0

    # Run drift detector
    detector = project_root / "scripts" / "architecture_drift_detector.py"
    if not detector.exists():
        print(json.dumps({"continue": True}))
        return 0

    try:
        result = subprocess.run(
            ["python", str(detector), "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=project_root,
        )
        data = json.loads(result.stdout)

        if data.get("has_drift"):
            # Show warning via blockMessage
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "shouldBlock": False,  # Don't block, just warn
                    "suppressOutput": False,
                }
            }
            # Print warning to stderr (visible to user)
            sys.stderr.write(
                "\n⚠️  DRIFT DETECTED - Run: python scripts/architecture_drift_detector.py --fix\n\n"
            )
            print(json.dumps(output))
            return 0

    except Exception:
        pass

    print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
