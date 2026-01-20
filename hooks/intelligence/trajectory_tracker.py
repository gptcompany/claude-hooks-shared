#!/usr/bin/env python3
"""Trajectory Tracker Hook - Traccia le trajectory degli agent per SONA learning.

Questo hook traccia l'esecuzione degli agent Task e registra:
- Inizio trajectory (PreToolUse Task)
- Step intermedi (PostToolUse Task)
- Fine trajectory (Stop)

Hook types: PreToolUse, PostToolUse, Stop (basato su --event argument)

Usage:
  trajectory_tracker.py --event=start   # PreToolUse
  trajectory_tracker.py --event=step    # PostToolUse
  trajectory_tracker.py --event=end     # Stop
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.mcp_client import (
        get_project_name,
        get_timestamp,
        memory_store,
        memory_retrieve,
    )
except ImportError:
    # Fallback - direct file access
    import json as _json

    MCP_STORE = Path.home() / ".claude-flow" / "memory" / "store.json"

    def get_project_name():
        return Path.cwd().name

    def get_timestamp():
        return datetime.now(timezone.utc).isoformat()

    def _load_store():
        MCP_STORE.parent.mkdir(parents=True, exist_ok=True)
        if MCP_STORE.exists():
            with open(MCP_STORE) as f:
                return _json.load(f)
        return {"entries": {}}

    def _save_store(store):
        with open(MCP_STORE, "w") as f:
            _json.dump(store, f, indent=2)

    def memory_store(key, value, namespace=""):
        store = _load_store()
        full_key = f"{namespace}:{key}" if namespace else key
        now = get_timestamp()
        store["entries"][full_key] = {
            "key": full_key,
            "value": value,
            "metadata": {},
            "storedAt": now,
            "accessCount": 0,
            "lastAccessed": now,
        }
        _save_store(store)
        return {"success": True}

    def memory_retrieve(key, namespace=""):
        store = _load_store()
        full_key = f"{namespace}:{key}" if namespace else key
        if full_key in store.get("entries", {}):
            return store["entries"][full_key].get("value")
        return None


# Logging
LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "trajectory_tracker.log"

# Active trajectory file (per-session state)
TRAJECTORY_FILE = LOG_DIR / "active_trajectory.json"


def log(msg: str):
    """Log message to file."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{get_timestamp()} - {msg}\n")
    except Exception:
        pass


def load_active_trajectory() -> dict | None:
    """Load active trajectory from file."""
    if TRAJECTORY_FILE.exists():
        try:
            with open(TRAJECTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_active_trajectory(trajectory: dict):
    """Save active trajectory to file."""
    with open(TRAJECTORY_FILE, "w") as f:
        json.dump(trajectory, f, indent=2)


def clear_active_trajectory():
    """Clear active trajectory file."""
    if TRAJECTORY_FILE.exists():
        TRAJECTORY_FILE.unlink()


def generate_trajectory_id() -> str:
    """Generate a unique trajectory ID."""
    import uuid

    return f"traj-{uuid.uuid4().hex[:8]}"


def on_start(hook_input: dict):
    """Handle PreToolUse Task - start new trajectory."""
    tool_input = hook_input.get("tool_input", {})
    task_description = tool_input.get(
        "description", tool_input.get("prompt", "unknown")
    )[:200]

    trajectory_id = generate_trajectory_id()
    project = get_project_name()
    now = get_timestamp()

    trajectory = {
        "id": trajectory_id,
        "project": project,
        "task": task_description,
        "started_at": now,
        "steps": [],
        "status": "in_progress",
    }

    # Save to active trajectory file
    save_active_trajectory(trajectory)

    # Store in MCP memory for persistence
    memory_store(f"trajectory:{project}:active", trajectory)

    log(f"Started trajectory {trajectory_id}: {task_description[:50]}...")

    # No output modification needed for PreToolUse
    return {}


def on_step(hook_input: dict):
    """Handle PostToolUse Task - record step."""
    trajectory = load_active_trajectory()
    if not trajectory:
        log("No active trajectory for step")
        return {}

    tool_result = hook_input.get("tool_result", {})
    tool_name = hook_input.get("tool_name", "Task")

    # Determine success from result
    success = True
    if isinstance(tool_result, dict):
        if tool_result.get("error"):
            success = False
    elif isinstance(tool_result, str) and "error" in tool_result.lower():
        success = False

    step = {
        "action": tool_name,
        "timestamp": get_timestamp(),
        "success": success,
        "quality": 1.0 if success else 0.5,
    }

    trajectory["steps"].append(step)
    save_active_trajectory(trajectory)

    log(f"Recorded step for {trajectory['id']}: {tool_name} (success={success})")

    return {}


def on_end(hook_input: dict):
    """Handle Stop - end trajectory and store for learning."""
    trajectory = load_active_trajectory()
    if not trajectory:
        log("No active trajectory to end")
        return {}

    project = get_project_name()
    now = get_timestamp()

    # Calculate overall success
    steps = trajectory.get("steps", [])
    if steps:
        success_rate = sum(1 for s in steps if s.get("success", False)) / len(steps)
        overall_success = success_rate >= 0.7
    else:
        overall_success = True
        success_rate = 1.0

    # Finalize trajectory
    trajectory["ended_at"] = now
    trajectory["status"] = "completed"
    trajectory["success"] = overall_success
    trajectory["success_rate"] = success_rate
    trajectory["total_steps"] = len(steps)

    # Store completed trajectory
    trajectory_id = trajectory["id"]
    memory_store(f"trajectory:{project}:{trajectory_id}", trajectory)

    # Update trajectory index
    index = memory_retrieve(f"trajectory:{project}:index") or []
    index.append(
        {
            "id": trajectory_id,
            "task": trajectory.get("task", "")[:100],
            "success": overall_success,
            "steps": len(steps),
            "timestamp": now,
        }
    )
    # Keep last 100 trajectories
    index = index[-100:]
    memory_store(f"trajectory:{project}:index", index)

    # Clear active trajectory
    clear_active_trajectory()

    # Clear MCP active marker
    memory_store(f"trajectory:{project}:active", None)

    log(
        f"Ended trajectory {trajectory_id}: success={overall_success}, steps={len(steps)}, rate={success_rate:.2f}"
    )

    return {}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Trajectory Tracker Hook")
    parser.add_argument(
        "--event",
        choices=["start", "step", "end"],
        required=True,
        help="Event type: start (PreToolUse), step (PostToolUse), end (Stop)",
    )
    args = parser.parse_args()

    # Read hook input from stdin
    hook_input = {}
    if not sys.stdin.isatty():
        try:
            hook_input = json.load(sys.stdin)
        except json.JSONDecodeError:
            pass

    try:
        if args.event == "start":
            result = on_start(hook_input)
        elif args.event == "step":
            result = on_step(hook_input)
        elif args.event == "end":
            result = on_end(hook_input)
        else:
            result = {}

        print(json.dumps(result))
        return 0

    except Exception as e:
        log(f"Error in {args.event}: {e}")
        print(json.dumps({}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
