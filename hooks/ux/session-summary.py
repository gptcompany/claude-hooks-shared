#!/media/sam/1TB/claude-hooks-shared/.venv/bin/python3
"""
Stop Hook: Session Summary

Shows a summary of the session metrics when Claude Code stops.
Uses Tips Engine v2 for evidence-based optimization suggestions.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add scripts directory to path for tips_engine imports
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

METRICS_DIR = Path.home() / ".claude" / "metrics"
EXPORT_SCRIPT = SCRIPTS_DIR / "metrics-export-questdb.py"
SESSION_STATE = METRICS_DIR / "session_state.json"
DAILY_LOG = METRICS_DIR / "daily.jsonl"
TIPS_FILE = METRICS_DIR / "last_session_tips.json"

# Import tips engine v2
try:
    from tips_engine import (
        SessionMetrics,
        generate_all_tips,
        format_tips_for_display,
        tips_to_dict,
        IndustryDefaults,
    )
    from questdb_client import get_historical_stats
    TIPS_ENGINE_AVAILABLE = True
except ImportError:
    TIPS_ENGINE_AVAILABLE = False


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


def generate_optimization_suggestions(session: dict, metrics: dict) -> list:
    """
    Generate actionable optimization suggestions based on session patterns.

    Returns list of (priority, suggestion) tuples.
    Priority: 1=high, 2=medium, 3=low
    """
    suggestions = []

    tool_calls = session.get("tool_calls", 0)
    errors = session.get("errors", 0)
    error_rate = errors / tool_calls if tool_calls > 0 else 0

    file_edits = metrics.get("file_edits", 0)
    reworks = metrics.get("reworks", 0)
    agent_spawns = metrics.get("agent_spawns", 0)
    agent_successes = metrics.get("agent_successes", 0)
    test_runs = metrics.get("test_runs", 0)
    tests_passed = metrics.get("tests_passed", 0)

    # 1. High rework rate - suggests insufficient planning
    if file_edits > 3 and reworks > file_edits * 0.3:
        rework_pct = (reworks / file_edits) * 100
        suggestions.append((1, f"High rework rate ({rework_pct:.0f}%): Use /tdd:cycle or plan before implementing"))

    # 2. High error rate - suggests command issues
    if tool_calls > 10 and error_rate > 0.15:
        suggestions.append((1, f"High error rate ({error_rate:.0%}): Check Bash commands syntax"))

    # 3. Agent overuse for simple tasks
    if agent_spawns > 5 and tool_calls > 0:
        agent_ratio = agent_spawns / tool_calls
        if agent_ratio > 0.2:
            suggestions.append((2, f"Consider direct Glob/Grep instead of Task agent for simple searches"))

    # 4. Agent failure rate
    if agent_spawns > 3 and agent_successes < agent_spawns * 0.7:
        success_rate = (agent_successes / agent_spawns) * 100
        suggestions.append((1, f"Low agent success ({success_rate:.0f}%): Check agent prompts clarity"))

    # 5. No tests run despite file changes
    if file_edits > 5 and test_runs == 0:
        suggestions.append((2, "Consider running tests after file changes: /tdd:cycle"))

    # 6. Low test pass rate
    if test_runs > 2 and tests_passed < test_runs * 0.6:
        pass_rate = (tests_passed / test_runs) * 100
        suggestions.append((1, f"Low test pass rate ({pass_rate:.0f}%): Focus on one test at a time"))

    # 7. Long session without checkpoints
    start_time = session.get("start_time")
    if start_time:
        duration = (datetime.now() - datetime.fromisoformat(start_time)).total_seconds()
        if duration > 1800 and tool_calls > 30:  # 30min+ with many tool calls
            suggestions.append((3, "Consider /undo:checkpoint for rollback safety"))

    # 8. Many tool calls without tasks
    tasks_completed = len(session.get("tasks_completed", []))
    if tool_calls > 20 and tasks_completed == 0:
        suggestions.append((3, "Track progress with TodoWrite for complex tasks"))

    return sorted(suggestions, key=lambda x: x[0])  # Sort by priority


def build_session_metrics(session: dict, metrics: dict) -> "SessionMetrics":
    """Convert session and metrics dicts to SessionMetrics dataclass."""
    if not TIPS_ENGINE_AVAILABLE:
        return None

    tool_calls = session.get("tool_calls", 0)
    errors = session.get("errors", 0)

    # Calculate duration
    duration = 0
    start_time = session.get("start_time")
    if start_time:
        duration = int((datetime.now() - datetime.fromisoformat(start_time)).total_seconds())

    # Get project from session or infer from cwd
    project = session.get("project", "")
    if not project:
        cwd = session.get("cwd", "")
        if cwd:
            project = Path(cwd).name

    return SessionMetrics(
        tool_calls=tool_calls,
        errors=errors,
        file_edits=metrics.get("file_edits", 0),
        reworks=metrics.get("reworks", 0),
        test_runs=metrics.get("test_runs", 0),
        tests_passed=metrics.get("tests_passed", 0),
        agent_spawns=metrics.get("agent_spawns", 0),
        agent_successes=metrics.get("agent_successes", 0),
        duration_seconds=duration,
        max_task_iterations=metrics.get("max_task_iterations", 0),
        stuck_tasks=metrics.get("stuck_tasks", 0),
        lines_changed=metrics.get("lines_changed", 0),
        files_modified=metrics.get("files_modified", 0),
        max_file_edits=metrics.get("max_file_edits", 0),
        max_file_reworks=metrics.get("max_file_reworks", 0),
        most_churned_file=metrics.get("most_churned_file", ""),
        project=project,
    )


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

    # Optimization suggestions - use Tips Engine v2 if available
    if TIPS_ENGINE_AVAILABLE:
        session_metrics = build_session_metrics(session, metrics)
        if session_metrics:
            project = session_metrics.project
            try:
                historical = get_historical_stats(project)
            except Exception:
                historical = IndustryDefaults.to_historical_stats()

            tips = generate_all_tips(session_metrics, historical)
            if tips:
                # Use tips_engine format
                cold_start = historical.data_source == "defaults"
                tips_display = format_tips_for_display(tips, cold_start=cold_start)
                lines.append(tips_display)
            else:
                lines.append("=" * 50 + "\n")
        else:
            lines.append("=" * 50 + "\n")
    else:
        # Fallback to legacy suggestions
        suggestions = generate_optimization_suggestions(session, metrics)
        if suggestions:
            lines.append("\n" + "-" * 50)
            lines.append("  OPTIMIZATION TIPS (Legacy)")
            lines.append("-" * 50)
            for priority, suggestion in suggestions[:3]:
                icon = "!" if priority == 1 else ">" if priority == 2 else "-"
                lines.append(f"  {icon} {suggestion}")
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

    # Generate and save tips for next session
    tips_data = None

    if TIPS_ENGINE_AVAILABLE:
        session_metrics = build_session_metrics(session, metrics)
        if session_metrics:
            project = session_metrics.project
            try:
                historical = get_historical_stats(project)
            except Exception:
                historical = IndustryDefaults.to_historical_stats()

            tips = generate_all_tips(session_metrics, historical)
            if tips:
                tips_data = tips_to_dict(tips, session_id, project, historical)
                tips_data["timestamp"] = datetime.now().isoformat()
                tips_data["summary"] = {
                    "duration_min": round((datetime.now() - datetime.fromisoformat(session.get("start_time", datetime.now().isoformat()))).total_seconds() / 60, 1) if session.get("start_time") else 0,
                    "tool_calls": tool_calls,
                    "errors": session.get("errors", 0),
                }
    else:
        # Fallback to legacy format
        suggestions = generate_optimization_suggestions(session, metrics)
        if suggestions:
            tips_data = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "tips": [{"priority": p, "tip": t} for p, t in suggestions],
                "summary": {
                    "duration_min": round((datetime.now() - datetime.fromisoformat(session.get("start_time", datetime.now().isoformat()))).total_seconds() / 60, 1) if session.get("start_time") else 0,
                    "tool_calls": tool_calls,
                    "errors": session.get("errors", 0),
                }
            }

    # Save tips for next session (user can choose to inject with /tips)
    if tips_data:
        try:
            TIPS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TIPS_FILE, "w") as f:
                json.dump(tips_data, f, indent=2)
        except Exception:
            pass

    # Build output
    output = {"notification": summary}
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
