#!/usr/bin/env python3
"""
Safe Hook Runner - Wraps any hook command to ensure it never crashes.

Usage in settings.json:
    "command": "python3 /path/to/run_safe.py /path/to/actual_hook.py"

Passes stdin to the hook and captures any errors, logging them for debugging.
"""

import json
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

LOG_FILE = Path.home() / ".claude" / "metrics" / "hook_errors.log"


def log_error(hook_path: str, error: str, stderr: str = ""):
    """Log error to file for debugging."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"\n[{datetime.now().isoformat()}] {hook_path}\n")
            f.write(f"Error: {error}\n")
            if stderr:
                f.write(f"Stderr: {stderr}\n")
            f.write("-" * 50 + "\n")
    except Exception:
        pass


def main():
    if len(sys.argv) < 2:
        print(json.dumps({}))
        sys.exit(0)

    hook_path = sys.argv[1]
    hook_args = sys.argv[2:]

    try:
        # Read stdin to pass to hook
        stdin_data = sys.stdin.read()

        # Run the actual hook
        # Use python3 explicitly for .py files to avoid permission/shebang issues
        if hook_path.endswith(".py"):
            cmd = ["python3", hook_path] + hook_args
        else:
            cmd = [hook_path] + hook_args

        result = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=9,  # Just under the 10s timeout in settings
        )

        # Pass through stdout (the hook's output)
        if result.stdout:
            print(result.stdout, end="")
        else:
            print(json.dumps({}))

        # Log stderr if any (for debugging)
        if result.stderr:
            log_error(hook_path, f"returncode={result.returncode}", result.stderr)

        sys.exit(0)

    except subprocess.TimeoutExpired:
        log_error(hook_path, "Timeout (9s)")
        print(json.dumps({}))
        sys.exit(0)

    except Exception as e:
        log_error(hook_path, str(e) + "\n" + traceback.format_exc())
        print(json.dumps({}))
        sys.exit(0)


if __name__ == "__main__":
    main()
