#!/usr/bin/env python3
"""
CI Auto-Fix Hook for Claude Code

Detects CI failures from pytest/gh run output and handles:
1. Auto-retry up to 3 times with exponential backoff
2. If retries exhausted, invoke ClaudeFlow for auto-fix

Triggers on: PostToolUse for Bash commands containing pytest, gh run, npm test
Output: Retry instruction or ClaudeFlow invocation

Hook Type: PostToolUse
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Configuration
MAX_RETRIES = 3
RETRY_STATE_FILE = Path.home() / ".claude" / "state" / "ci_retry_state.json"

# Patterns to detect CI commands
CI_COMMAND_PATTERNS = [
    r"\bpytest\b",
    r"\bnpm\s+test\b",
    r"\bgh\s+run\b",
    r"\bmake\s+test\b",
    r"\bcargo\s+test\b",
    r"\bgo\s+test\b",
]

# Patterns to detect failures
FAILURE_PATTERNS = [
    r"FAILED",
    r"ERRORS?:",
    r"AssertionError",
    r"Error:",
    r"error\[",
    r"npm ERR!",
    r"FAIL\s",
    r"failure",
    r"panic:",
]

# Paths for logging
METRICS_DIR = Path.home() / ".claude" / "metrics"
CI_LOG = METRICS_DIR / "ci_autofix.jsonl"


def log_event(event_type: str, data: dict):
    """Log CI auto-fix events."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        **data,
    }
    with open(CI_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_retry_state() -> dict:
    """Load retry state from file."""
    RETRY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if RETRY_STATE_FILE.exists():
        try:
            return json.loads(RETRY_STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_retry_state(state: dict):
    """Save retry state to file."""
    RETRY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RETRY_STATE_FILE.write_text(json.dumps(state, indent=2))


def get_test_key(command: str) -> str:
    """Generate a unique key for the test command."""
    # Extract test file or pattern
    match = re.search(r"(?:pytest|test)\s+([^\s]+)", command)
    if match:
        return f"test:{match.group(1)}"
    return f"cmd:{hash(command) % 10000}"


def is_ci_command(command: str) -> bool:
    """Check if command is a CI/test command."""
    return any(re.search(pattern, command, re.IGNORECASE) for pattern in CI_COMMAND_PATTERNS)


def has_failure(output: str) -> bool:
    """Check if output contains failure indicators."""
    return any(re.search(pattern, output, re.IGNORECASE) for pattern in FAILURE_PATTERNS)


def extract_error_context(output: str, command: str) -> dict:
    """Extract error context from output for ClaudeFlow."""
    context = {
        "command": command,
        "error_message": "",
        "file_path": "",
        "stack_trace": "",
        "test_name": "",
    }

    # Extract first error message
    error_match = re.search(r"((?:Error|FAILED|AssertionError)[^\n]+)", output)
    if error_match:
        context["error_message"] = error_match.group(1)

    # Extract file path from pytest output
    file_match = re.search(r"([^\s]+\.py):(\d+)", output)
    if file_match:
        context["file_path"] = file_match.group(1)
        context["line_number"] = file_match.group(2)

    # Extract test name
    test_match = re.search(r"(test_\w+)", output)
    if test_match:
        context["test_name"] = test_match.group(1)

    # Extract stack trace (last 20 lines before error)
    lines = output.split("\n")
    for i, line in enumerate(lines):
        if re.search(r"(?:Error|FAILED)", line, re.IGNORECASE):
            start = max(0, i - 20)
            context["stack_trace"] = "\n".join(lines[start : i + 5])
            break

    return context


def generate_fix_instruction(error_context: dict) -> str:
    """Generate fix instruction for Claude."""
    instruction = f"""
🔴 **CI FAILURE - Auto-Fix Required**

## Error
{error_context["error_message"]}

## Location
`{error_context.get("file_path", "Unknown")}:{error_context.get("line_number", "?")}`

## Test
`{error_context.get("test_name", "Unknown")}`

## Stack Trace
```
{error_context.get("stack_trace", "Not available")[:500]}
```

**Action Required:**
1. Read the failing file
2. Analyze the root cause
3. Fix the code
4. Re-run the test: `{error_context["command"]}`
"""
    log_event("fix_instruction_generated", {"context": error_context})
    return instruction


def main():
    """Main hook entry point."""
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Check if this is a Bash tool use
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    # Get command and output
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    tool_result = input_data.get("tool_result", "")

    # Check if it's a CI command
    if not is_ci_command(command):
        sys.exit(0)

    # Check if there's a failure
    if not has_failure(tool_result):
        # Success - clear retry state for this test
        test_key = get_test_key(command)
        state = get_retry_state()
        if test_key in state:
            del state[test_key]
            save_retry_state(state)
        sys.exit(0)

    # We have a failure
    test_key = get_test_key(command)
    state = get_retry_state()

    # Get current retry count
    retry_info = state.get(test_key, {"count": 0, "first_failure": datetime.now().isoformat()})
    retry_count = retry_info["count"]

    if retry_count < MAX_RETRIES:
        # Auto-retry with exponential backoff
        retry_count += 1
        delay = 2**retry_count  # 2, 4, 8 seconds

        state[test_key] = {
            "count": retry_count,
            "first_failure": retry_info.get("first_failure", datetime.now().isoformat()),
            "last_retry": datetime.now().isoformat(),
        }
        save_retry_state(state)

        log_event(
            "retry_scheduled",
            {"test_key": test_key, "retry_count": retry_count, "delay": delay},
        )

        # Output message for Claude to see
        msg = f"CI failure detected (attempt {retry_count}/{MAX_RETRIES}). Auto-retry in {delay}s recommended."
        result = {
            "continue": True,
            "message": f"{msg}\nRun the command again: {command}",
        }
        print(json.dumps(result))

    else:
        # Retries exhausted - generate fix instruction for Claude
        error_context = extract_error_context(tool_result, command)

        log_event(
            "retries_exhausted",
            {
                "test_key": test_key,
                "retry_count": retry_count,
                "error": error_context["error_message"],
            },
        )

        # Clear retry state
        if test_key in state:
            del state[test_key]
            save_retry_state(state)

        # Generate fix instruction
        fix_instruction = generate_fix_instruction(error_context)

        result = {
            "continue": True,
            "message": fix_instruction,
        }
        print(json.dumps(result))


if __name__ == "__main__":
    main()
