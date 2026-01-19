#!/usr/bin/env python3
"""
Safe Hook Wrapper - Ensures hooks never crash with unhandled exceptions.

Usage in hook:
    from hooks.core.safe_hook_wrapper import safe_main

    def main():
        # your hook logic
        pass

    if __name__ == "__main__":
        safe_main(main)
"""

import json
import sys
import traceback
from pathlib import Path

LOG_FILE = Path.home() / ".claude" / "metrics" / "hook_errors.log"


def safe_main(hook_func, hook_name: str = "unknown"):
    """
    Wrap a hook's main function with comprehensive error handling.

    Ensures the hook NEVER raises an exception - always exits cleanly.
    Logs errors to ~/.claude/metrics/hook_errors.log for debugging.
    """
    try:
        hook_func()
    except Exception as e:
        # Log error for debugging
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a") as f:
                from datetime import datetime

                f.write(f"\n[{datetime.now().isoformat()}] {hook_name}\n")
                f.write(f"Error: {e}\n")
                f.write(traceback.format_exc())
                f.write("-" * 50 + "\n")
        except Exception:
            pass  # Even logging failed, just continue

        # Exit cleanly with empty JSON (success)
        print(json.dumps({}))
        sys.exit(0)


def wrap_hook(hook_name: str):
    """
    Decorator to wrap hook main functions.

    Usage:
        @wrap_hook("my-hook")
        def main():
            # hook logic
            pass
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            safe_main(lambda: func(*args, **kwargs), hook_name)

        return wrapper

    return decorator
