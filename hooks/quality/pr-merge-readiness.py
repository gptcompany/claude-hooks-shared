#!/usr/bin/env python3
"""
PostToolUse Hook: PR Merge Readiness Checker

After gh pr create/view commands, checks if PR is ready for merge.
Provides actionable feedback on what's blocking merge.

Checks:
- Tests pass (CI status)
- Lint clean (CI status)
- No merge conflicts
- Required reviews approved
- All checks green
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Cooldown to avoid repeated checks on same PR
COOLDOWN_FILE = Path.home() / ".claude" / "pr_readiness_cooldown.json"
COOLDOWN_SECONDS = 300  # 5 minutes between checks for same PR


def get_pr_number_from_output(output: str) -> int | None:
    """Extract PR number from gh command output."""
    # Match patterns like "pull/123" or "#123" or "PR #123"
    patterns = [
        r"pull/(\d+)",
        r"#(\d+)",
        r"PR\s+#?(\d+)",
        r"github\.com/[^/]+/[^/]+/pull/(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
    return None


def is_in_cooldown(pr_number: int) -> bool:
    """Check if we recently checked this PR."""
    try:
        if not COOLDOWN_FILE.exists():
            return False
        data = json.loads(COOLDOWN_FILE.read_text())
        last_check = data.get(str(pr_number), 0)
        return (datetime.now().timestamp() - last_check) < COOLDOWN_SECONDS
    except (json.JSONDecodeError, OSError):
        return False


def update_cooldown(pr_number: int) -> None:
    """Update cooldown for PR."""
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if COOLDOWN_FILE.exists():
            try:
                data = json.loads(COOLDOWN_FILE.read_text())
            except json.JSONDecodeError:
                pass
        # Clean old entries
        now = datetime.now().timestamp()
        data = {k: v for k, v in data.items() if now - v < 3600}
        data[str(pr_number)] = now
        COOLDOWN_FILE.write_text(json.dumps(data))
    except (OSError, PermissionError):
        pass


def check_pr_status(pr_number: int) -> dict:
    """Check PR readiness using gh CLI."""
    checks = {
        "mergeable": {"status": "unknown", "message": ""},
        "ci_status": {"status": "unknown", "message": ""},
        "reviews": {"status": "unknown", "message": ""},
        "conflicts": {"status": "unknown", "message": ""},
    }

    try:
        # Get PR details
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--json",
                "mergeable,state,reviewDecision,statusCheckRollup,mergeStateStatus",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return checks

        pr_data = json.loads(result.stdout)

        # Check mergeable state
        mergeable = pr_data.get("mergeable", "UNKNOWN")
        merge_state = pr_data.get("mergeStateStatus", "UNKNOWN")

        if mergeable == "MERGEABLE":
            checks["mergeable"] = {"status": "pass", "message": "PR is mergeable"}
        elif mergeable == "CONFLICTING":
            checks["mergeable"] = {"status": "fail", "message": "Has merge conflicts"}
            checks["conflicts"] = {"status": "fail", "message": "Resolve conflicts first"}
        else:
            checks["mergeable"] = {"status": "pending", "message": f"State: {merge_state}"}

        # Check CI status
        status_checks = pr_data.get("statusCheckRollup", [])
        if status_checks:
            failed = [c for c in status_checks if c.get("conclusion") == "FAILURE"]
            pending = [c for c in status_checks if c.get("status") == "IN_PROGRESS"]
            passed = [c for c in status_checks if c.get("conclusion") == "SUCCESS"]

            if failed:
                checks["ci_status"] = {
                    "status": "fail",
                    "message": f"{len(failed)} check(s) failed: {', '.join(c.get('name', '?') for c in failed[:3])}",
                }
            elif pending:
                checks["ci_status"] = {"status": "pending", "message": f"{len(pending)} check(s) in progress"}
            elif passed:
                checks["ci_status"] = {"status": "pass", "message": f"All {len(passed)} checks passed"}
        else:
            checks["ci_status"] = {"status": "skip", "message": "No CI checks configured"}

        # Check reviews
        review_decision = pr_data.get("reviewDecision", "")
        if review_decision == "APPROVED":
            checks["reviews"] = {"status": "pass", "message": "Approved"}
        elif review_decision == "CHANGES_REQUESTED":
            checks["reviews"] = {"status": "fail", "message": "Changes requested"}
        elif review_decision == "REVIEW_REQUIRED":
            checks["reviews"] = {"status": "pending", "message": "Review required"}
        else:
            checks["reviews"] = {"status": "skip", "message": "No review required"}

        # Conflicts (already set above if CONFLICTING)
        if checks["conflicts"]["status"] == "unknown":
            checks["conflicts"] = {"status": "pass", "message": "No conflicts"}

    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        checks["mergeable"] = {"status": "error", "message": str(e)[:50]}

    return checks


def format_readiness_report(pr_number: int, checks: dict) -> str:
    """Format readiness report for display."""
    icons = {
        "pass": "\u2705",  # Green check
        "fail": "\u274c",  # Red X
        "pending": "\u23f3",  # Hourglass
        "skip": "\u23ed",  # Skip
        "unknown": "\u2753",  # Question
        "error": "\u26a0",  # Warning
    }

    lines = [f"**PR #{pr_number} Merge Readiness**", ""]

    all_pass = True
    has_blocker = False

    for check_name, check_data in checks.items():
        status = check_data["status"]
        icon = icons.get(status, "\u2753")
        message = check_data["message"]

        display_name = check_name.replace("_", " ").title()
        lines.append(f"{icon} **{display_name}**: {message}")

        if status == "fail":
            has_blocker = True
            all_pass = False
        elif status not in ("pass", "skip"):
            all_pass = False

    lines.append("")

    if all_pass:
        lines.append("\u2728 **Ready to merge!**")
    elif has_blocker:
        lines.append("\u26d4 **Blockers must be resolved before merge**")
    else:
        lines.append("\u23f3 **Waiting for checks to complete**")

    return "\n".join(lines)


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Only process Bash tool with gh pr commands
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        print(json.dumps({}))
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Check if this is a gh pr command
    if "gh pr" not in command and "gh pr" not in str(input_data.get("tool_result", "")):
        print(json.dumps({}))
        sys.exit(0)

    # Extract PR number from command or output
    tool_result = input_data.get("tool_result", "")
    if isinstance(tool_result, dict):
        output = tool_result.get("stdout", "") + tool_result.get("stderr", "")
    else:
        output = str(tool_result)

    pr_number = get_pr_number_from_output(command + " " + output)

    if not pr_number:
        print(json.dumps({}))
        sys.exit(0)

    # Check cooldown
    if is_in_cooldown(pr_number):
        print(json.dumps({}))
        sys.exit(0)

    # Update cooldown
    update_cooldown(pr_number)

    # Check PR status
    checks = check_pr_status(pr_number)

    # Format report
    report = format_readiness_report(pr_number, checks)

    response = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "message": f"PR #{pr_number} readiness checked",
        },
        "notification": report,
    }

    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
