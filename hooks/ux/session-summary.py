#!/usr/bin/env python3
"""
Stop Hook: Session Summary

Shows a summary of the session metrics when Claude Code stops.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"
# Use relative path from hook location for portability
EXPORT_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "metrics-export-questdb.py"
SESSION_STATE = METRICS_DIR / "session_state.json"
DAILY_LOG = METRICS_DIR / "daily.jsonl"


def get_session_stats() -> dict:
    """Get current session statistics."""
    if not SESSION_STATE.exists():
        return {}

    try:
        return json.loads(SESSION_STATE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def get_session_metrics(session_id: str) -> dict:
    """Get metrics for this session from daily log."""
    if not DAILY_LOG.exists():
        return {}

    metrics = {
        "file_edits": 0,
        "reworks": 0,
        "test_runs": 0,
        "tests_passed": 0,
        "agent_spawns": 0,
        "agent_successes": 0,
        "tasks_completed": 0,
    }

    with open(DAILY_LOG) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("session_id") != session_id:
                    continue

                entry_type = entry.get("type")
                if entry_type == "file_edit":
                    metrics["file_edits"] += 1
                    if entry.get("is_rework"):
                        metrics["reworks"] += 1
                elif entry_type == "test_run":
                    metrics["test_runs"] += 1
                    if entry.get("passed"):
                        metrics["tests_passed"] += 1
                elif entry_type == "agent_spawn":
                    metrics["agent_spawns"] += 1
                    if entry.get("success", True):
                        metrics["agent_successes"] += 1
                elif entry_type == "cycle_time":
                    metrics["tasks_completed"] += 1
            except json.JSONDecodeError:
                continue

    return metrics


def format_duration(seconds: float) -> str:
    """Format duration in human readable form."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.0f}m"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:.0f}h {minutes:.0f}m"


def generate_summary(session: dict, metrics: dict) -> str:
    """Generate session summary message."""
    lines = ["\n" + "=" * 50]
    lines.append("  SESSION SUMMARY")
    lines.append("=" * 50)

    # Duration
    start_time = session.get("start_time")
    if start_time:
        start = datetime.fromisoformat(start_time)
        duration = (datetime.now() - start).total_seconds()
        lines.append(f"\n  Duration:        {format_duration(duration)}")

    # Tool calls
    tool_calls = session.get("tool_calls", 0)
    errors = session.get("errors", 0)
    error_rate = errors / tool_calls if tool_calls > 0 else 0
    lines.append(f"  Tool Calls:      {tool_calls}")
    if errors > 0:
        lines.append(f"  Errors:          {errors} ({error_rate:.1%})")

    # File edits
    if metrics.get("file_edits", 0) > 0:
        lines.append(f"\n  File Edits:      {metrics['file_edits']}")
        if metrics.get("reworks", 0) > 0:
            lines.append(f"  Reworks:         {metrics['reworks']}")

    # Tests
    if metrics.get("test_runs", 0) > 0:
        passed = metrics.get("tests_passed", 0)
        total = metrics.get("test_runs", 0)
        lines.append(f"\n  Tests Run:       {total}")
        lines.append(f"  Tests Passed:    {passed} ({passed / total:.0%})")

    # Agents
    if metrics.get("agent_spawns", 0) > 0:
        spawns = metrics.get("agent_spawns", 0)
        successes = metrics.get("agent_successes", 0)
        lines.append(f"\n  Agents Used:     {spawns}")
        lines.append(f"  Agent Success:   {successes / spawns:.0%}")

    # Tasks
    tasks_completed = len(session.get("tasks_completed", []))
    if tasks_completed > 0:
        lines.append(f"\n  Tasks Completed: {tasks_completed}")

    # Health indicator
    lines.append("\n" + "-" * 50)
    if error_rate < 0.1 and metrics.get("reworks", 0) <= metrics.get("file_edits", 1) * 0.2:
        lines.append("  Status: Good session!")
    elif error_rate > 0.2:
        lines.append("  Status: High error rate - review commands")
    elif metrics.get("reworks", 0) > metrics.get("file_edits", 1) * 0.3:
        lines.append("  Status: High rework - consider planning more")
    else:
        lines.append("  Status: Normal session")

    lines.append("=" * 50 + "\n")

    return "\n".join(lines)


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Get session data
    session = get_session_stats()
    session_id = session.get("session_id", "unknown")

    # Get metrics for this session
    metrics = get_session_metrics(session_id)

    # Only show summary if there was activity
    tool_calls = session.get("tool_calls", 0)
    if tool_calls < 5:
        # Too short session, skip summary
        print(json.dumps({}))
        sys.exit(0)

    # Generate summary
    summary = generate_summary(session, metrics)

    # Log final session stats
    if DAILY_LOG.parent.exists():
        with open(DAILY_LOG, "a") as f:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "session_end",
                "session_id": session_id,
                "duration_seconds": (
                    datetime.now()
                    - datetime.fromisoformat(session.get("start_time", datetime.now().isoformat()))
                ).total_seconds()
                if session.get("start_time")
                else 0,
                "tool_calls": tool_calls,
                "errors": session.get("errors", 0),
                "tasks_completed": len(session.get("tasks_completed", [])),
            }
            f.write(json.dumps(entry) + "\n")

    # Export metrics to QuestDB (async, don't block)
    # Uses --days 1 for recent metrics
    # QuestDB dedup handles duplicates (same timestamp = overwrite)
    if EXPORT_SCRIPT.exists():
        try:
            subprocess.Popen(
                ["python3", str(EXPORT_SCRIPT), "--days", "1", "--quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass  # Don't fail session end if export fails

    # Return notification
    output = {"notification": summary}
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
