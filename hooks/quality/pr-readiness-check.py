#!/usr/bin/env python3
"""
PR Readiness Check Hook for Claude Code

Evaluates PR readiness using ensemble scoring from multiple criteria:
1. Git Diff Size - Sufficient changes (>50 lines)
2. Phase Completion - All tasks in current phase completed
3. Tests Passing - All tests green
4. Coverage Level - Coverage > 90% for critical modules
5. Alpha-Debug Clean - No bugs found in last run

Triggers on: gh pr create commands
Output: Readiness score with detailed breakdown

Weights:
- Git Diff: 10% (informational, not blocking)
- Phase Complete: 25% (important for scope)
- Tests Green: 30% (critical - blocking if red)
- Coverage: 20% (important for quality)
- Alpha-Debug: 15% (important for hidden bugs)
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configuration
WEIGHTS = {
    "git_diff": 0.10,
    "phase_complete": 0.25,
    "tests_green": 0.30,
    "coverage": 0.20,
    "ralph_loop": 0.15,
}

# Thresholds
MIN_DIFF_LINES = 50
MIN_COVERAGE = 90
READY_THRESHOLD = 80
WARNING_THRESHOLD = 60

# Paths
METRICS_DIR = Path.home() / ".claude" / "metrics"
PR_CHECK_LOG = METRICS_DIR / "pr_readiness.jsonl"


def log_pr_check(data: dict):
    """Log PR readiness check results."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now().isoformat(), **data}
    with open(PR_CHECK_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_git_diff_stats() -> dict:
    """Get git diff statistics."""
    try:
        # Get diff against main/master
        for base in ["main", "master", "develop"]:
            result = subprocess.run(
                ["git", "diff", "--stat", f"{base}...HEAD"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                break
        else:
            # Fallback to uncommitted changes
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                capture_output=True,
                text=True,
            )

        output = result.stdout.strip()
        if not output:
            return {"lines_added": 0, "lines_removed": 0, "files_changed": 0, "score": 0}

        # Parse stats line: "X files changed, Y insertions(+), Z deletions(-)"
        stats_match = re.search(
            r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?",
            output,
        )
        if stats_match:
            files = int(stats_match.group(1) or 0)
            added = int(stats_match.group(2) or 0)
            removed = int(stats_match.group(3) or 0)
            total = added + removed

            # Score: 100 if >= MIN_DIFF_LINES, proportional otherwise
            score = min(100, (total / MIN_DIFF_LINES) * 100) if MIN_DIFF_LINES > 0 else 100

            return {
                "lines_added": added,
                "lines_removed": removed,
                "files_changed": files,
                "total_lines": total,
                "score": round(score),
            }

    except subprocess.CalledProcessError:
        pass

    return {"lines_added": 0, "lines_removed": 0, "files_changed": 0, "score": 0}


def check_phase_completion() -> dict:
    """Check if current phase tasks are completed."""
    # Look for tasks.md in common locations
    tasks_paths = [
        Path.cwd() / "tasks.md",
        Path.cwd() / "specs" / "tasks.md",
        Path.cwd() / ".speckit" / "tasks.md",
    ]

    # Also check parent directories
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents)[:3]:
        tasks_paths.append(parent / "tasks.md")

    for tasks_path in tasks_paths:
        if tasks_path.exists():
            content = tasks_path.read_text()

            # Count tasks by status
            # Pattern: - [x] completed, - [ ] pending, - [~] in progress
            completed = len(re.findall(r"- \[x\]", content, re.IGNORECASE))
            pending = len(re.findall(r"- \[ \]", content))
            in_progress = len(re.findall(r"- \[~\]", content))

            total = completed + pending + in_progress
            if total == 0:
                return {"status": "no_tasks", "score": 50, "message": "No tasks found"}

            # Find current phase (look for ## Phase N or similar headers)
            phase_match = re.search(
                r"##\s*(Phase\s*\d+|Current Phase)[^\n]*\n(.*?)(?=##|\Z)",
                content,
                re.DOTALL | re.IGNORECASE,
            )

            if phase_match:
                phase_content = phase_match.group(2)
                phase_completed = len(re.findall(r"- \[x\]", phase_content, re.IGNORECASE))
                phase_pending = len(re.findall(r"- \[ \]", phase_content))
                phase_in_progress = len(re.findall(r"- \[~\]", phase_content))
                phase_total = phase_completed + phase_pending + phase_in_progress

                if phase_total > 0:
                    score = (phase_completed / phase_total) * 100
                    return {
                        "status": "phase_found",
                        "phase_completed": phase_completed,
                        "phase_total": phase_total,
                        "score": round(score),
                        "message": f"Phase: {phase_completed}/{phase_total} tasks done",
                    }

            # Fallback to overall completion
            score = (completed / total) * 100
            return {
                "status": "overall",
                "completed": completed,
                "total": total,
                "score": round(score),
                "message": f"Overall: {completed}/{total} tasks done",
            }

    return {"status": "no_tasks_file", "score": 50, "message": "No tasks.md found"}


def check_tests_passing() -> dict:
    """Check if tests are passing (from recent test run)."""
    # Check for recent pytest results
    test_results_paths = [
        Path.home() / ".claude" / "metrics" / "test_results.json",
        Path.cwd() / ".pytest_cache" / "v" / "cache" / "lastfailed",
        Path.cwd() / "test-results.json",
    ]

    for path in test_results_paths:
        if path.exists():
            try:
                if "lastfailed" in str(path):
                    # pytest lastfailed cache - empty means all passed
                    content = path.read_text().strip()
                    if content == "{}" or not content:
                        return {"status": "green", "score": 100, "message": "All tests passing"}
                    else:
                        failed_count = content.count('"')  # Rough count
                        return {
                            "status": "red",
                            "score": 0,
                            "message": "Some tests failing",
                            "failed": failed_count,
                        }
                else:
                    data = json.loads(path.read_text())
                    passed = data.get("passed", 0)
                    failed = data.get("failed", 0)
                    total = passed + failed
                    if total > 0:
                        score = (passed / total) * 100
                        status = "green" if failed == 0 else "red"
                        return {
                            "status": status,
                            "passed": passed,
                            "failed": failed,
                            "score": round(score),
                            "message": f"{passed}/{total} tests passing",
                        }
            except (json.JSONDecodeError, OSError):
                pass

    # Try running quick test check
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # If last commit mentions tests passing, assume good
        if (
            result.returncode == 0
            and "test" in result.stdout.lower()
            and "pass" in result.stdout.lower()
        ):
            return {
                "status": "inferred_green",
                "score": 80,
                "message": "Tests likely passing (from commit)",
            }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    return {"status": "unknown", "score": 50, "message": "Test status unknown - run tests first"}


def check_coverage() -> dict:
    """Check code coverage level."""
    coverage_paths = [
        Path.cwd() / "coverage.json",
        Path.cwd() / ".coverage.json",
        Path.cwd() / "htmlcov" / "status.json",
        Path.home() / ".claude" / "metrics" / "coverage.json",
    ]

    for path in coverage_paths:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                # Handle different coverage.py output formats
                if "totals" in data:
                    coverage_pct = data["totals"].get("percent_covered", 0)
                elif "meta" in data:
                    coverage_pct = data.get("totals", {}).get("percent_covered", 0)
                else:
                    coverage_pct = data.get("coverage", data.get("percent", 0))

                score = min(100, (coverage_pct / MIN_COVERAGE) * 100)
                status = "good" if coverage_pct >= MIN_COVERAGE else "low"

                return {
                    "status": status,
                    "coverage_pct": round(coverage_pct, 1),
                    "score": round(score),
                    "message": f"Coverage: {coverage_pct:.1f}%",
                }
            except (json.JSONDecodeError, OSError, KeyError):
                pass

    # Check for coverage in pytest output
    try:
        result = subprocess.run(
            ["git", "log", "-5", "--format=%b"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            cov_match = re.search(
                r"(\d+(?:\.\d+)?)\s*%\s*(?:coverage|cov)", result.stdout, re.IGNORECASE
            )
            if cov_match:
                coverage_pct = float(cov_match.group(1))
                score = min(100, (coverage_pct / MIN_COVERAGE) * 100)
                return {
                    "status": "inferred",
                    "coverage_pct": coverage_pct,
                    "score": round(score),
                    "message": f"Coverage (from commits): {coverage_pct}%",
                }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    return {"status": "unknown", "score": 50, "message": "Coverage unknown - run with --cov"}


def check_ralph_loop() -> dict:
    """Check Ralph Loop results."""
    # Look for Ralph state and logs
    ralph_paths = [
        Path.home() / ".claude" / "ralph" / "state.json",
        Path.home() / ".claude" / "metrics" / "ralph_iterations.jsonl",
    ]

    # Check state file first
    state_path = ralph_paths[0]
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            if state.get("active"):
                return {
                    "status": "in_progress",
                    "score": 70,
                    "message": f"Ralph Loop active (iteration {state.get('iteration', 0)})",
                }

            exit_reason = state.get("exit_reason", "")
            if "complete" in exit_reason.lower() or "pass" in exit_reason.lower():
                return {
                    "status": "complete",
                    "score": 100,
                    "message": f"Ralph Loop: {exit_reason}",
                }
            elif exit_reason:
                return {
                    "status": "stopped",
                    "score": 60,
                    "message": f"Ralph Loop stopped: {exit_reason}",
                }
        except (json.JSONDecodeError, OSError):
            pass

    # Check log file for recent activity
    log_path = ralph_paths[1]
    if log_path.exists():
        try:
            lines = log_path.read_text().strip().split("\n")
            if lines:
                last_entry = json.loads(lines[-1])
                timestamp = last_entry.get("timestamp", "")

                if timestamp:
                    try:
                        entry_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        age_hours = (
                            datetime.now(entry_time.tzinfo) - entry_time
                        ).total_seconds() / 3600
                        if age_hours > 24:
                            return {
                                "status": "stale",
                                "score": 50,
                                "message": "Ralph Loop results stale (>24h)",
                            }
                    except (ValueError, TypeError):
                        pass

                return {
                    "status": "ran",
                    "score": 80,
                    "message": "Ralph Loop ran recently",
                }
        except (json.JSONDecodeError, OSError):
            pass

    return {"status": "not_run", "score": 50, "message": "Ralph Loop not run recently"}


def calculate_ensemble_score(criteria: dict) -> dict:
    """Calculate weighted ensemble score."""
    total_score = 0
    weighted_breakdown = {}

    for criterion, data in criteria.items():
        weight = WEIGHTS.get(criterion, 0)
        score = data.get("score", 0)
        weighted_score = score * weight
        total_score += weighted_score
        weighted_breakdown[criterion] = {
            "raw_score": score,
            "weight": weight,
            "weighted": round(weighted_score, 1),
        }

    return {
        "total_score": round(total_score),
        "breakdown": weighted_breakdown,
    }


def format_output(criteria: dict, ensemble: dict) -> str:
    """Format output for user display."""
    total = ensemble["total_score"]

    # Determine status
    if total >= READY_THRESHOLD:
        status_emoji = "\U0001f7e2"  # Green circle
        status_text = "READY"
    elif total >= WARNING_THRESHOLD:
        status_emoji = "\U0001f7e1"  # Yellow circle
        status_text = "CAUTION"
    else:
        status_emoji = "\U0001f534"  # Red circle
        status_text = "NOT READY"

    lines = [
        "",
        f"{status_emoji} PR READINESS: {status_text} (Score: {total}/100)",
        "\u2550" * 50,
        "",
        "CRITERIA BREAKDOWN:",
        "",
    ]

    # Format each criterion
    criterion_names = {
        "git_diff": "Git Diff Size",
        "phase_complete": "Phase Complete",
        "tests_green": "Tests Passing",
        "coverage": "Code Coverage",
        "ralph_loop": "Ralph Loop",
    }

    for criterion, data in criteria.items():
        name = criterion_names.get(criterion, criterion)
        score = data.get("score", 0)
        message = data.get("message", "")
        weight = WEIGHTS.get(criterion, 0)
        weighted = score * weight

        # Score bar
        bar_filled = int(score / 10)
        bar = "\u2588" * bar_filled + "\u2591" * (10 - bar_filled)

        lines.append(f"  {name:18} [{bar}] {score:3}% x {weight:.0%} = {weighted:.1f}")
        if message:
            lines.append(f"                      {message}")
        lines.append("")

    lines.extend(
        [
            "\u2550" * 50,
            f"ENSEMBLE SCORE: {total}/100",
            "",
        ]
    )

    # Add recommendations
    if total < READY_THRESHOLD:
        lines.append("RECOMMENDATIONS:")
        if criteria.get("tests_green", {}).get("status") == "red":
            lines.append("  \u2022 Fix failing tests before creating PR")
        if criteria.get("tests_green", {}).get("status") == "unknown":
            lines.append("  \u2022 Run tests: uv run pytest tests/ -v")
        if criteria.get("coverage", {}).get("score", 100) < 90:
            lines.append("  \u2022 Improve coverage: uv run pytest --cov --cov-report=json")
        if criteria.get("ralph_loop", {}).get("status") == "not_run":
            lines.append("  \u2022 Run Ralph Loop for iterative debugging")
        if criteria.get("phase_complete", {}).get("score", 100) < 100:
            lines.append("  \u2022 Complete remaining tasks in current phase")
        lines.append("")

    return "\n".join(lines)


def main():
    """Main hook logic."""
    try:
        input_data = json.loads(sys.stdin.read())
        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")

        # Only trigger on gh pr create commands
        if "gh" not in command or "pr" not in command or "create" not in command:
            sys.exit(0)

        # Gather all criteria
        criteria = {
            "git_diff": get_git_diff_stats(),
            "phase_complete": check_phase_completion(),
            "tests_green": check_tests_passing(),
            "coverage": check_coverage(),
            "ralph_loop": check_ralph_loop(),
        }

        # Calculate ensemble score
        ensemble = calculate_ensemble_score(criteria)
        total_score = ensemble["total_score"]

        # Log results
        log_pr_check(
            {
                "criteria": criteria,
                "ensemble": ensemble,
                "cwd": str(Path.cwd()),
            }
        )

        # Format output
        output_message = format_output(criteria, ensemble)

        # Determine if we should block
        should_block = False
        block_reasons = []

        # Block if tests are failing
        if criteria.get("tests_green", {}).get("status") == "red":
            should_block = True
            block_reasons.append("Tests are failing")

        # Block if score is very low
        if total_score < 40:
            should_block = True
            block_reasons.append(f"Readiness score too low ({total_score}/100)")

        if should_block:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "shouldBlock": True,
                    "blockMessage": output_message
                    + "\n\n\u274c BLOCKED: "
                    + ", ".join(block_reasons),
                }
            }
            print(json.dumps(output))
            sys.exit(1)

        # Show as informational message
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "shouldBlock": False,
                "message": output_message,
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception as e:
        # Fail open
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "message": f"\u26a0\ufe0f PR readiness check error: {str(e)}",
                    }
                }
            )
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
