#!/usr/bin/env python3
"""
Quality Score Tracker Hook

PostToolUse hook that analyzes tool outputs (pytest, ruff, mypy, etc.)
and calculates a weighted quality score per commit/session.

Weight Distribution:
- code: 25% (ruff + mypy + bandit)
- test: 30% (coverage + pass rate)
- data: 25% (pandera/schema compliance)
- framework: 20% (speckit/gsd verification)

Writes to QuestDB: claude_quality_scores table
Alerts Discord if total < 70
"""

import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

QUESTDB_HOST = "localhost"
QUESTDB_PORT = 9009

# Discord webhook for alerts (from environment)
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_QUALITY", "")

# Score weights
WEIGHTS = {
    "code": 0.25,
    "test": 0.30,
    "data": 0.25,
    "framework": 0.20,
}

# Alert threshold
ALERT_THRESHOLD = 70


def escape_tag(value: str) -> str:
    """Escape special characters in ILP tag values."""
    return str(value).replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def send_to_questdb(line: str) -> bool:
    """Send single ILP line to QuestDB."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((QUESTDB_HOST, QUESTDB_PORT))
            s.sendall((line + "\n").encode())
        return True
    except Exception as e:
        print(f"QuestDB error: {e}", file=sys.stderr)
        return False


def send_discord_alert(project: str, score: float, breakdown: dict) -> None:
    """Send Discord alert for low quality score."""
    if not DISCORD_WEBHOOK:
        return

    try:
        import urllib.request

        message = {
            "embeds": [
                {
                    "title": f"Quality Alert: {project}",
                    "description": f"Quality score dropped below {ALERT_THRESHOLD}",
                    "color": 15158332,  # Red
                    "fields": [
                        {"name": "Total Score", "value": f"{score:.1f}", "inline": True},
                        {"name": "Code", "value": f"{breakdown.get('code', 0):.1f}", "inline": True},
                        {"name": "Test", "value": f"{breakdown.get('test', 0):.1f}", "inline": True},
                        {"name": "Data", "value": f"{breakdown.get('data', 0):.1f}", "inline": True},
                        {"name": "Framework", "value": f"{breakdown.get('framework', 0):.1f}", "inline": True},
                    ],
                }
            ]
        }

        req = urllib.request.Request(
            DISCORD_WEBHOOK,
            data=json.dumps(message).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Silent fail for alerts


def detect_project() -> str:
    """Detect current project from working directory."""
    cwd = os.getcwd()

    project_map = {
        "/media/sam/1TB/nautilus_dev": "nautilus",
        "/media/sam/1TB/UTXOracle": "utxoracle",
        "/media/sam/1TB/claude-flow": "claudeflow",
        "/media/sam/1TB/LiquidationHeatmap": "liquidation",
        "/media/sam/1TB/N8N_dev": "n8n",
    }

    for path, name in project_map.items():
        if cwd.startswith(path):
            return name

    return Path(cwd).name


def get_git_info() -> tuple[str, str]:
    """Get current git commit hash and branch."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()

        return commit or "unknown", branch or "unknown"
    except Exception:
        return "unknown", "unknown"


def parse_pytest_output(output: str) -> dict:
    """Parse pytest output for pass rate and coverage."""
    result = {"pass_rate": 100, "coverage": 0, "passed": 0, "failed": 0}

    # Parse test results: "5 passed, 2 failed"
    match = re.search(r"(\d+)\s+passed", output)
    if match:
        result["passed"] = int(match.group(1))

    match = re.search(r"(\d+)\s+failed", output)
    if match:
        result["failed"] = int(match.group(1))

    total = result["passed"] + result["failed"]
    if total > 0:
        result["pass_rate"] = (result["passed"] / total) * 100

    # Parse coverage: "TOTAL ... 85%"
    match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
    if match:
        result["coverage"] = int(match.group(1))

    # Alternative: "Coverage: 85%"
    match = re.search(r"Coverage[:\s]+(\d+)%", output, re.IGNORECASE)
    if match:
        result["coverage"] = int(match.group(1))

    return result


def parse_ruff_output(output: str) -> dict:
    """Parse ruff output for linting score."""
    result = {"errors": 0, "warnings": 0, "score": 100}

    # Count errors/warnings
    error_matches = re.findall(r"^.+:\d+:\d+: [EF]\d+", output, re.MULTILINE)
    warning_matches = re.findall(r"^.+:\d+:\d+: [WC]\d+", output, re.MULTILINE)

    result["errors"] = len(error_matches)
    result["warnings"] = len(warning_matches)

    # Score: 100 - (errors * 5 + warnings * 1)
    result["score"] = max(0, 100 - (result["errors"] * 5 + result["warnings"] * 1))

    # Alternative: "Found X errors"
    match = re.search(r"Found (\d+) errors?", output)
    if match:
        result["errors"] = int(match.group(1))
        result["score"] = max(0, 100 - result["errors"] * 5)

    # If "All checks passed" or similar
    if "All checks passed" in output or "no issues found" in output.lower():
        result["score"] = 100

    return result


def parse_mypy_output(output: str) -> dict:
    """Parse mypy output for type checking score."""
    result = {"errors": 0, "score": 100}

    # "Found X errors"
    match = re.search(r"Found (\d+) errors?", output)
    if match:
        result["errors"] = int(match.group(1))
        result["score"] = max(0, 100 - result["errors"] * 3)

    # Count error lines
    error_lines = re.findall(r"^.+:\d+: error:", output, re.MULTILINE)
    if error_lines and not match:
        result["errors"] = len(error_lines)
        result["score"] = max(0, 100 - result["errors"] * 3)

    # Success message
    if "Success" in output or "no issues found" in output.lower():
        result["score"] = 100

    return result


def calculate_scores(tool_output: str, command: str) -> dict:
    """Calculate quality scores from tool output."""
    scores = {
        "code": None,
        "test": None,
        "data": None,
        "framework": None,
    }

    command_lower = command.lower()

    # Test score (pytest)
    if "pytest" in command_lower:
        pytest_data = parse_pytest_output(tool_output)
        # Test score = (pass_rate * 0.6) + (coverage * 0.4)
        coverage = pytest_data.get("coverage", 0)
        pass_rate = pytest_data.get("pass_rate", 100)
        scores["test"] = (pass_rate * 0.6) + (coverage * 0.4)

    # Code score (ruff)
    if "ruff" in command_lower:
        ruff_data = parse_ruff_output(tool_output)
        scores["code"] = ruff_data.get("score", 100)

    # Code score (mypy) - combine with ruff if both present
    if "mypy" in command_lower:
        mypy_data = parse_mypy_output(tool_output)
        if scores["code"] is not None:
            scores["code"] = (scores["code"] + mypy_data.get("score", 100)) / 2
        else:
            scores["code"] = mypy_data.get("score", 100)

    # Data score (pandera)
    if "pandera" in tool_output.lower() or "schema" in command_lower:
        # Simple heuristic: no schema errors = 100
        if "SchemaError" in tool_output or "ValidationError" in tool_output:
            scores["data"] = 50
        else:
            scores["data"] = 100

    # Framework score (speckit/gsd)
    if "speckit" in command_lower or "gsd" in command_lower:
        if "error" in tool_output.lower() or "failed" in tool_output.lower():
            scores["framework"] = 70
        else:
            scores["framework"] = 100

    return scores


def main():
    """Main hook function - called as PostToolUse hook."""
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        input_data = {}

    tool_name = input_data.get("tool_name", "")
    tool_output = input_data.get("tool_output", "")
    tool_input = input_data.get("tool_input", {})

    # Only process Bash tool outputs
    if tool_name != "Bash":
        print(json.dumps({"status": "skipped", "reason": "not Bash tool"}))
        return

    command = tool_input.get("command", "")

    # Check if command is relevant for quality scoring
    relevant_commands = ["pytest", "ruff", "mypy", "bandit", "speckit", "gsd"]
    if not any(cmd in command.lower() for cmd in relevant_commands):
        print(json.dumps({"status": "skipped", "reason": "not quality-related command"}))
        return

    # Calculate scores
    scores = calculate_scores(tool_output, command)

    # Filter out None values
    active_scores = {k: v for k, v in scores.items() if v is not None}

    if not active_scores:
        print(json.dumps({"status": "skipped", "reason": "no scores calculated"}))
        return

    # Calculate weighted total
    total_weight = sum(WEIGHTS[k] for k in active_scores)
    total_score = sum(scores[k] * WEIGHTS[k] for k in active_scores) / total_weight if total_weight > 0 else 0

    # Get project and git info
    project = detect_project()
    commit, branch = get_git_info()
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")

    # Determine block/category
    if "pytest" in command.lower():
        block = "test"
    elif any(x in command.lower() for x in ["ruff", "mypy", "bandit"]):
        block = "code"
    elif "speckit" in command.lower() or "gsd" in command.lower():
        block = "framework"
    else:
        block = "general"

    # Build ILP line
    ts_now = int(datetime.utcnow().timestamp() * 1e9)

    line = (
        f"claude_quality_scores,"
        f"project={escape_tag(project)},"
        f"block={escape_tag(block)},"
        f"branch={escape_tag(branch)} "
        f"score_total={total_score},"
        f"score_code={scores.get('code') or 0},"
        f"score_test={scores.get('test') or 0},"
        f"score_data={scores.get('data') or 0},"
        f"score_framework={scores.get('framework') or 0},"
        f'commit_hash="{commit}",'
        f'session_id="{session_id}" '
        f"{ts_now}"
    )

    # Send to QuestDB
    sent = send_to_questdb(line)

    # Alert if score is low
    if total_score < ALERT_THRESHOLD:
        send_discord_alert(project, total_score, active_scores)

    # Output result
    result = {
        "status": "tracked",
        "project": project,
        "block": block,
        "total_score": round(total_score, 2),
        "scores": {k: round(v, 2) for k, v in active_scores.items()},
        "sent_to_questdb": sent,
        "alert_triggered": total_score < ALERT_THRESHOLD,
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
