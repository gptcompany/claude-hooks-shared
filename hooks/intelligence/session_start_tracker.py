#!/usr/bin/env python3
"""
Session Start Tracker - UserPromptSubmit Hook

Tracks the git state at session start for comparison at session end.
Works with session-analyzer.py to enable intelligent diff-based suggestions.

Runs on FIRST prompt of session only (detects new session).
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"
SESSION_STATE_FILE = METRICS_DIR / "session_state.json"
LAST_SESSION_STATS_FILE = METRICS_DIR / "last_session_stats.json"
INSIGHTS_FILE = METRICS_DIR / "session_insights.json"  # SSOT
SESSION_TIMEOUT_MINUTES = 30  # New session if > 30 min since last activity
MAX_STATS_AGE_HOURS = 24  # Ignore stats older than this


def get_current_commit() -> str | None:
    """Get current HEAD commit."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_current_branch() -> str | None:
    """Get current branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_repo_root() -> str | None:
    """Get git repository root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def is_new_session() -> bool:
    """Determine if this is a new session (vs continuation)."""
    if not SESSION_STATE_FILE.exists():
        return True

    try:
        state = json.loads(SESSION_STATE_FILE.read_text())
        last_activity = state.get("last_activity")

        if not last_activity:
            return True

        last_dt = datetime.fromisoformat(last_activity)
        elapsed = (datetime.now() - last_dt).total_seconds() / 60

        # New session if timeout exceeded
        if elapsed > SESSION_TIMEOUT_MINUTES:
            return True

        # Same repo?
        current_repo = get_repo_root()
        if current_repo and state.get("repo_root") != current_repo:
            return True

        return False

    except (json.JSONDecodeError, ValueError, OSError):
        return True


def save_session_state(is_new: bool):
    """Save or update session state."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()

    if is_new:
        # New session - record starting state
        state = {
            "session_start": now,
            "start_commit": get_current_commit(),
            "start_branch": get_current_branch(),
            "repo_root": get_repo_root(),
            "last_activity": now,
            "prompt_count": 1,
        }
    else:
        # Existing session - just update activity
        try:
            state = json.loads(SESSION_STATE_FILE.read_text())
            state["last_activity"] = now
            state["prompt_count"] = state.get("prompt_count", 0) + 1
        except (json.JSONDecodeError, OSError):
            # Corrupted state, start fresh
            state = {
                "session_start": now,
                "start_commit": get_current_commit(),
                "start_branch": get_current_branch(),
                "repo_root": get_repo_root(),
                "last_activity": now,
                "prompt_count": 1,
            }

    SESSION_STATE_FILE.write_text(json.dumps(state, indent=2))
    return state


def get_previous_session_stats() -> dict | None:
    """Load stats from previous session if recent enough."""
    if not LAST_SESSION_STATS_FILE.exists():
        return None

    try:
        stats = json.loads(LAST_SESSION_STATS_FILE.read_text())
        timestamp = stats.get("timestamp")

        if not timestamp:
            return None

        # Check age
        stats_dt = datetime.fromisoformat(timestamp)
        age_hours = (datetime.now() - stats_dt).total_seconds() / 3600

        if age_hours > MAX_STATS_AGE_HOURS:
            return None

        return stats

    except (json.JSONDecodeError, ValueError, OSError):
        return None


def clear_previous_session_stats() -> None:
    """Clear stats after injecting (prevent repeated injection)."""
    try:
        if LAST_SESSION_STATS_FILE.exists():
            LAST_SESSION_STATS_FILE.unlink()
    except OSError:
        pass


def get_previous_insights() -> str | None:
    """Load SSOT insights from previous session and format compactly."""
    if not INSIGHTS_FILE.exists():
        return None

    try:
        data = json.loads(INSIGHTS_FILE.read_text())
        timestamp = data.get("ended_at")

        # Check age
        if timestamp:
            ended_dt = datetime.fromisoformat(timestamp)
            age_hours = (datetime.now() - ended_dt).total_seconds() / 3600
            if age_hours > MAX_STATS_AGE_HOURS:
                return None

        # Format compact output
        parts = []

        # Context percentage
        if ctx := data.get("context"):
            pct = ctx.get("percentage", 0)
            status = ctx.get("status", "normal")
            if status == "critical":
                parts.append(f"{pct}% ctx!")
            elif status == "warning":
                parts.append(f"{pct}% ctx")

        # Summary stats
        if summary := data.get("summary"):
            calls = summary.get("tool_calls", 0)
            errors = summary.get("errors", 0)
            if calls:
                parts.append(f"{calls} calls")
            if errors:
                parts.append(f"{errors} err")

        # Git status
        if git := data.get("git"):
            if git.get("uncommitted"):
                added = git.get("lines_added", 0)
                removed = git.get("lines_removed", 0)
                parts.append(f"uncommitted +{added}/-{removed}")

        # Delegation recommendation
        if data.get("delegation", {}).get("recommended"):
            parts.append("DELEGATE!")

        # High-confidence tips with category breakdown + top command
        tips = data.get("tips", [])
        high_conf_tips = [t for t in tips if t.get("confidence", 0) >= 0.7]
        if high_conf_tips:
            # Compact format: category counts + top command suggestion
            categories: dict[str, int] = {}
            for t in high_conf_tips:
                cat = t.get("category", "general")
                categories[cat] = categories.get(cat, 0) + 1

            cat_summary = "/".join(f"{c}:{n}" for c, n in sorted(categories.items()))
            top_cmd = high_conf_tips[0].get("command", "")

            parts.append(f"{len(high_conf_tips)} tips ({cat_summary})")
            if top_cmd:
                parts.append(f"try: {top_cmd}")

        return ", ".join(parts) if parts else None

    except (json.JSONDecodeError, ValueError, OSError):
        return None


def clear_previous_insights() -> None:
    """Clear SSOT after injecting (prevent repeated injection)."""
    try:
        if INSIGHTS_FILE.exists():
            INSIGHTS_FILE.unlink()
    except OSError:
        pass


def main():
    try:
        _input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Check if new session
    is_new = is_new_session()

    # Save state
    state = save_session_state(is_new)

    # Build output
    context_parts = []

    # For new sessions, inject previous session insights
    if is_new:
        # Try SSOT first
        insights_summary = get_previous_insights()
        if insights_summary:
            context_parts.append(f"[prev: {insights_summary}]")
            clear_previous_insights()  # One-time injection
        else:
            # Fallback to legacy format
            prev_stats = get_previous_session_stats()
            if prev_stats and prev_stats.get("formatted"):
                context_parts.append(f"[prev session: {prev_stats['formatted']}]")
                clear_previous_session_stats()  # One-time injection

        if state.get("start_commit"):
            context_parts.append(f"[tracking: {state['start_branch']}@{state['start_commit'][:8]}]")

    if context_parts:
        output = {
            "additionalContext": " ".join(context_parts),
        }
        print(json.dumps(output))
    else:
        print(json.dumps({}))

    sys.exit(0)


if __name__ == "__main__":
    main()
