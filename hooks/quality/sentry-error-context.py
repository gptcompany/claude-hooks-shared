#!/usr/bin/env python3
"""
PostToolUse Hook: Sentry Error Context Provider

After Bash commands with errors (exit code != 0), this hook:
1. Extracts error patterns from output
2. Queries Sentry for related issues
3. Provides historical context to help debugging

Enterprise integration for automated error correlation.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Configuration
SENTRY_ORG = os.environ.get("SENTRY_ORG", "gptprojectmanager")
SENTRY_REGION = os.environ.get("SENTRY_REGION", "https://de.sentry.io")
MIN_ERROR_LENGTH = 20  # Minimum error text length to query
COOLDOWN_SECONDS = 60  # Avoid querying for same error pattern
COOLDOWN_FILE = Path.home() / ".claude" / "sentry_query_cooldown.json"

# Error patterns to extract
ERROR_PATTERNS = [
    r"(?:Error|Exception|Failed|FAILED):\s*(.+?)(?:\n|$)",
    r"(?:error\[E\d+\]):\s*(.+?)(?:\n|$)",  # Rust errors
    r"(?:TypeError|ValueError|KeyError|AttributeError|ImportError):\s*(.+?)(?:\n|$)",
    r"(?:AssertionError):\s*(.+?)(?:\n|$)",
    r"FAILED\s+(\S+::\S+)",  # pytest failures
    r"ModuleNotFoundError:\s*(.+?)(?:\n|$)",
]


def extract_error_patterns(output: str) -> list[str]:
    """Extract meaningful error patterns from command output."""
    errors = []
    for pattern in ERROR_PATTERNS:
        matches = re.findall(pattern, output, re.IGNORECASE | re.MULTILINE)
        errors.extend(matches)

    # Deduplicate and filter
    seen = set()
    unique_errors = []
    for err in errors:
        err_clean = err.strip()[:200]  # Limit length
        if err_clean and len(err_clean) >= MIN_ERROR_LENGTH and err_clean not in seen:
            seen.add(err_clean)
            unique_errors.append(err_clean)

    return unique_errors[:3]  # Max 3 patterns


def is_in_cooldown(error_pattern: str) -> bool:
    """Check if we recently queried for this error pattern."""
    try:
        if not COOLDOWN_FILE.exists():
            return False

        data = json.loads(COOLDOWN_FILE.read_text())
        last_query = data.get(error_pattern, 0)

        return (datetime.now().timestamp() - last_query) < COOLDOWN_SECONDS
    except (json.JSONDecodeError, OSError):
        return False


def update_cooldown(error_pattern: str) -> None:
    """Update cooldown timestamp for error pattern."""
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        if COOLDOWN_FILE.exists():
            try:
                data = json.loads(COOLDOWN_FILE.read_text())
            except json.JSONDecodeError:
                pass

        # Keep only recent entries (last hour)
        now = datetime.now().timestamp()
        data = {k: v for k, v in data.items() if now - v < 3600}
        data[error_pattern] = now

        COOLDOWN_FILE.write_text(json.dumps(data))
    except (OSError, PermissionError):
        pass


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Only process Bash tool
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        print(json.dumps({}))
        sys.exit(0)

    # Check for errors in output
    tool_result = input_data.get("tool_result", {})

    # Handle different result formats
    if isinstance(tool_result, dict):
        stdout = tool_result.get("stdout", "")
        stderr = tool_result.get("stderr", "")
        exit_code = tool_result.get("exitCode", 0)
    elif isinstance(tool_result, str):
        stdout = tool_result
        stderr = ""
        # Infer error from content
        exit_code = 1 if any(p in stdout.lower() for p in ["error", "failed", "exception"]) else 0
    else:
        print(json.dumps({}))
        sys.exit(0)

    # Only process errors
    combined_output = f"{stdout}\n{stderr}"
    if exit_code == 0 and not any(
        p in combined_output.lower() for p in ["error", "failed", "exception"]
    ):
        print(json.dumps({}))
        sys.exit(0)

    # Extract error patterns
    errors = extract_error_patterns(combined_output)
    if not errors:
        print(json.dumps({}))
        sys.exit(0)

    # Check cooldown for first error
    primary_error = errors[0]
    if is_in_cooldown(primary_error):
        print(json.dumps({}))
        sys.exit(0)

    # Update cooldown
    update_cooldown(primary_error)

    # Build Sentry query suggestion
    error_summary = errors[0][:100]

    response = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "message": "🔍 Sentry: Error detected. Query for context?",
        },
        "notification": f"""
**Sentry Error Context Available**

Detected error pattern: `{error_summary}`

To query Sentry for related issues:
```
mcp__sentry__search_issues(
  organizationSlug="{SENTRY_ORG}",
  naturalLanguageQuery="{error_summary[:50]}",
  regionUrl="{SENTRY_REGION}"
)
```

Or use Seer for root cause analysis on specific issues.
""",
    }

    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
