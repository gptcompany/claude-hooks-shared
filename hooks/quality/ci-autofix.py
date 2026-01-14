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
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configuration
MAX_RETRIES = 3
RETRY_STATE_FILE = Path.home() / ".claude" / "state" / "ci_retry_state.json"
CLAUDEFLOW_BIN = Path("/media/sam/1TB/claude-flow/bin/pair-autofix-only.js")
CLAUDEFLOW_ENDPOINT = "http://localhost:3847/auto-fix"

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
    for pattern in CI_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def has_failure(output: str) -> bool:
    """Check if output contains failure indicators."""
    for pattern in FAILURE_PATTERNS:
        if re.search(pattern, output, re.IGNORECASE):
            return True
    return False


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


def invoke_claudeflow(error_context: dict) -> bool:
    """Invoke ClaudeFlow for auto-fix."""
    prompt = f"""
CI Failure detected. Please analyze and fix:

## Command
{error_context["command"]}

## Error
{error_context["error_message"]}

## File
{error_context.get("file_path", "Unknown")}:{error_context.get("line_number", "?")}

## Test
{error_context.get("test_name", "Unknown")}

## Stack Trace
```
{error_context.get("stack_trace", "Not available")}
```

Please:
1. Analyze the root cause
2. Fix the code
3. Re-run the test to verify
"""

    log_event("claudeflow_invoked", {"context": error_context})

    # Try HTTP endpoint first (if ClaudeFlow server is running)
    try:
        import requests

        response = requests.post(
            CLAUDEFLOW_ENDPOINT,
            json={"prompt": prompt, "context": error_context},
            timeout=5,
        )
        if response.ok:
            log_event("claudeflow_success", {"method": "http"})
            return True
    except Exception:
        pass  # Fall through to subprocess

    # Fallback to direct invocation
    if CLAUDEFLOW_BIN.exists():
        try:
            result = subprocess.run(
                ["node", str(CLAUDEFLOW_BIN), "--prompt", prompt],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            log_event(
                "claudeflow_result",
                {"returncode": result.returncode, "method": "subprocess"},
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            log_event("claudeflow_timeout", {})
            return False
        except Exception as e:
            log_event("claudeflow_error", {"error": str(e)})
            return False

    log_event("claudeflow_not_available", {})
    return False


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
        result = {
            "continue": True,
            "message": f"CI failure detected (attempt {retry_count}/{MAX_RETRIES}). Auto-retry in {delay}s recommended.\n"
            f"Run the command again: {command}",
        }
        print(json.dumps(result))

    else:
        # Retries exhausted - invoke ClaudeFlow
        error_context = extract_error_context(tool_result, command)

        log_event(
            "retries_exhausted",
            {"test_key": test_key, "retry_count": retry_count, "error": error_context["error_message"]},
        )

        # Clear retry state
        if test_key in state:
            del state[test_key]
            save_retry_state(state)

        # Invoke ClaudeFlow
        success = invoke_claudeflow(error_context)

        result = {
            "continue": True,
            "message": f"CI failure persists after {MAX_RETRIES} retries. "
            f"{'ClaudeFlow auto-fix triggered.' if success else 'ClaudeFlow not available - manual fix needed.'}\n"
            f"Error: {error_context['error_message']}",
        }
        print(json.dumps(result))


if __name__ == "__main__":
    main()
