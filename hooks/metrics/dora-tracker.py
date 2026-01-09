#!/usr/bin/env python3
"""
PostToolUse Hook: DORA Metrics Tracker

Tracks basic DORA-inspired metrics for Claude Code sessions:
- Cycle time (time between task start and completion)
- Rework rate (edits to same file within 24h)
- Task completion rate
- Test pass rate
- Session stats (duration, tool calls, errors)

Logs to ~/.claude/metrics/daily.jsonl for analysis.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Metrics storage
METRICS_DIR = Path.home() / ".claude" / "metrics"
DAILY_LOG = METRICS_DIR / "daily.jsonl"
FILE_EDIT_LOG = METRICS_DIR / "file_edits.json"
SESSION_STATE = METRICS_DIR / "session_state.json"


def ensure_metrics_dir():
    """Create metrics directory if not exists."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)


def get_session_state() -> dict:
    """Load or initialize session state for tracking."""
    if SESSION_STATE.exists():
        try:
            return json.loads(SESSION_STATE.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Initialize new session
    return {
        "session_id": os.environ.get(
            "CLAUDE_SESSION_ID", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ),
        "start_time": datetime.now().isoformat(),
        "tool_calls": 0,
        "errors": 0,
        "model": os.environ.get("CLAUDE_MODEL", "unknown"),
        "tasks_started": [],
        "tasks_completed": [],
        "task_iterations": {},  # task_id -> iteration count
    }


def save_session_state(state: dict):
    """Save session state."""
    ensure_metrics_dir()
    SESSION_STATE.write_text(json.dumps(state, indent=2))


def update_session_stats(tool_name: str, success: bool):
    """Update session statistics."""
    state = get_session_state()
    state["tool_calls"] = state.get("tool_calls", 0) + 1
    if not success:
        state["errors"] = state.get("errors", 0) + 1
    state["last_activity"] = datetime.now().isoformat()
    save_session_state(state)
    return state


def track_task_cycle(task_id: str, status: str):
    """Track task start/completion for cycle time and iterations."""
    state = get_session_state()
    now = datetime.now().isoformat()

    if status == "in_progress":
        if task_id not in [t["id"] for t in state.get("tasks_started", [])]:
            state.setdefault("tasks_started", []).append(
                {
                    "id": task_id,
                    "start_time": now,
                }
            )
            # Initialize iteration counter
            state.setdefault("task_iterations", {})[task_id] = 0
    elif status == "completed":
        # Find matching start
        started = state.get("tasks_started", [])
        for task in started:
            if task["id"] == task_id:
                cycle_time_seconds = (
                    datetime.fromisoformat(now) - datetime.fromisoformat(task["start_time"])
                ).total_seconds()

                iterations = state.get("task_iterations", {}).get(task_id, 0)

                state.setdefault("tasks_completed", []).append(
                    {
                        "id": task_id,
                        "start_time": task["start_time"],
                        "end_time": now,
                        "cycle_time_seconds": cycle_time_seconds,
                        "iterations": iterations,
                    }
                )

                # Log cycle time metric with iterations
                log_metric(
                    "cycle_time",
                    {
                        "task_id": task_id,
                        "cycle_time_seconds": cycle_time_seconds,
                        "cycle_time_minutes": cycle_time_seconds / 60,
                        "iterations": iterations,
                    },
                )

                # Clean up iteration counter
                state.get("task_iterations", {}).pop(task_id, None)
                break

    save_session_state(state)


def increment_task_iterations():
    """Increment iteration count for all active tasks."""
    state = get_session_state()
    task_iterations = state.get("task_iterations", {})

    for task_id in task_iterations:
        task_iterations[task_id] += 1

    state["task_iterations"] = task_iterations
    save_session_state(state)


def load_file_edits() -> dict:
    """Load file edit history for rework tracking."""
    if FILE_EDIT_LOG.exists():
        try:
            return json.loads(FILE_EDIT_LOG.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_file_edits(edits: dict):
    """Save file edit history."""
    ensure_metrics_dir()
    FILE_EDIT_LOG.write_text(json.dumps(edits, indent=2))


def calculate_rework_rate(file_path: str) -> float:
    """Calculate if this is a rework (edit within 24h of last edit)."""
    edits = load_file_edits()
    now = datetime.now().timestamp()

    if file_path in edits:
        last_edit = edits[file_path]["last_edit"]
        hours_since = (now - last_edit) / 3600

        if hours_since < 24:
            edits[file_path]["rework_count"] = edits[file_path].get("rework_count", 0) + 1
            edits[file_path]["last_edit"] = now
            save_file_edits(edits)
            return 1.0  # This is a rework

    # New file or first edit in 24h
    edits[file_path] = {
        "last_edit": now,
        "rework_count": edits.get(file_path, {}).get("rework_count", 0),
    }
    save_file_edits(edits)
    return 0.0


def get_project_name() -> str:
    """Get project name from git repo or environment."""
    # Try environment first
    env_name = os.environ.get("CLAUDE_PROJECT_NAME", "")
    if env_name and env_name != "unknown":
        return env_name

    # Try git repo name
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except Exception:
        pass

    # Fallback to current directory name
    return Path.cwd().name


def get_git_info() -> dict:
    """Get current git commit info for correlation."""
    try:
        import subprocess

        # Get current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        commit = result.stdout.strip() if result.returncode == 0 else None

        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        branch = result.stdout.strip() if result.returncode == 0 else None

        return {"commit": commit, "branch": branch}
    except Exception:
        return {"commit": None, "branch": None}


def log_metric(metric_type: str, data: dict):
    """Append metric to daily log."""
    ensure_metrics_dir()

    git_info = get_git_info()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": metric_type,
        "project": get_project_name(),
        "session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
        "git_commit": git_info.get("commit"),
        "git_branch": git_info.get("branch"),
        **data,
    }

    with open(DAILY_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    # Track file edits for rework rate
    if tool_name in ["Write", "Edit", "MultiEdit"]:
        file_path = tool_input.get("file_path", "")
        if file_path:
            rework = calculate_rework_rate(file_path)
            log_metric("file_edit", {"file": file_path, "tool": tool_name, "is_rework": rework > 0})

    # Track test runs
    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if "pytest" in command or "test" in command.lower():
            # Try to detect pass/fail from response
            response_text = str(tool_response)
            passed = "passed" in response_text.lower() and "failed" not in response_text.lower()

            log_metric(
                "test_run",
                {
                    "command": command[:200],  # Truncate
                    "passed": passed,
                },
            )

    # Track Task/Agent spawns and results
    elif tool_name == "Task":
        agent_type = tool_input.get("subagent_type", "unknown")
        description = tool_input.get("description", "")[:100]

        # Detect success/failure from response
        response_text = str(tool_response).lower()
        success = not any(
            err in response_text
            for err in ["error", "failed", "exception", "traceback", "cannot", "unable"]
        )

        log_metric(
            "agent_spawn",
            {
                "agent_type": agent_type,
                "description": description,
                "success": success,
            },
        )

    # Track todo completions and cycle time
    elif tool_name == "TodoWrite":
        todos = tool_input.get("todos", [])
        completed = sum(1 for t in todos if t.get("status") == "completed")
        in_progress = [t for t in todos if t.get("status") == "in_progress"]
        total = len(todos)

        log_metric(
            "todo_update",
            {
                "total": total,
                "completed": completed,
                "completion_rate": completed / total if total > 0 else 0,
            },
        )

        # Track cycle time for tasks
        for todo in todos:
            task_id = todo.get("content", "")[:50]  # Use content as ID
            status = todo.get("status", "")
            if status in ["in_progress", "completed"]:
                track_task_cycle(task_id, status)

    # Update session stats for all tools
    response_text = str(tool_response)
    success = "error" not in response_text.lower()
    session_state = update_session_stats(tool_name, success)

    # Increment iterations for active tasks
    increment_task_iterations()

    # Log session summary periodically (every 10 calls)
    if session_state.get("tool_calls", 0) % 10 == 0:
        log_metric(
            "session_stats",
            {
                "tool_calls": session_state.get("tool_calls", 0),
                "errors": session_state.get("errors", 0),
                "error_rate": session_state.get("errors", 0)
                / max(session_state.get("tool_calls", 1), 1),
                "model": session_state.get("model", "unknown"),
                "tasks_completed": len(session_state.get("tasks_completed", [])),
            },
        )

    # Check for threshold alerts (every 20 calls)
    alerts = []
    if session_state.get("tool_calls", 0) % 20 == 0 and session_state.get("tool_calls", 0) > 0:
        alerts = check_thresholds(session_state)

    if alerts:
        alert_msg = "\n".join([f"  {a}" for a in alerts])
        output = {
            "notification": f"\n{'=' * 40}\n  METRICS ALERT\n{'=' * 40}\n{alert_msg}\n{'=' * 40}\n"
        }
        print(json.dumps(output))
    else:
        # Pass through - this hook doesn't modify anything
        print(json.dumps({}))
    sys.exit(0)


def check_thresholds(session_state: dict) -> list[str]:
    """Check if any metrics exceed thresholds."""
    alerts = []

    # Error rate threshold
    tool_calls = session_state.get("tool_calls", 0)
    errors = session_state.get("errors", 0)
    if tool_calls > 10:
        error_rate = errors / tool_calls
        if error_rate > 0.15:
            alerts.append(f"High error rate: {error_rate:.1%} (threshold: 15%)")

    # Rework rate - check file_edits.json
    try:
        file_edits = load_file_edits()
        if file_edits:
            total_edits = len(file_edits)
            reworks = sum(1 for f, d in file_edits.items() if d.get("rework_count", 0) > 0)
            if total_edits > 5:
                rework_rate = reworks / total_edits
                if rework_rate > 0.3:
                    alerts.append(f"High rework rate: {rework_rate:.1%} (threshold: 30%)")
    except Exception:
        pass

    return alerts


if __name__ == "__main__":
    main()
