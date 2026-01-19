#!/media/sam/1TB/claude-hooks-shared/.venv/bin/python3
"""
UserPromptSubmit Hook: Auto-inject tips from previous session.

Injects optimization tips into context at the start of a new session.
Only triggers once per session (first prompt after session start).
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"
SESSION_STATE = METRICS_DIR / "session_state.json"
TIPS_FILE = METRICS_DIR / "last_session_tips.json"
SSOT_FILE = METRICS_DIR / "session_insights.json"
INJECTED_MARKER = METRICS_DIR / ".tips_injected"

# Max age for tips to be considered relevant (hours)
MAX_TIPS_AGE_HOURS = 24


def get_session_id() -> str:
    """Get current session ID or generate one from session_start timestamp."""
    if not SESSION_STATE.exists():
        return ""
    try:
        data = json.loads(SESSION_STATE.read_text())
        # Try session_id first, fallback to session_start timestamp
        session_id = data.get("session_id")
        if session_id:
            return session_id
        # Use session_start as unique identifier
        session_start = data.get("session_start")
        if session_start:
            return f"session_{session_start}"
        return ""
    except (json.JSONDecodeError, OSError):
        return ""


def was_already_injected(session_id: str) -> bool:
    """Check if tips were already injected for this session."""
    if not INJECTED_MARKER.exists():
        return False
    try:
        marker = json.loads(INJECTED_MARKER.read_text())
        return marker.get("session_id") == session_id
    except (json.JSONDecodeError, OSError):
        return False


def mark_injected(session_id: str) -> None:
    """Mark tips as injected for this session."""
    try:
        INJECTED_MARKER.parent.mkdir(parents=True, exist_ok=True)
        INJECTED_MARKER.write_text(json.dumps({"session_id": session_id, "timestamp": datetime.now().isoformat()}))
    except OSError:
        pass


def load_tips() -> dict | None:
    """Load tips from SSOT or fallback to legacy file."""
    # Try SSOT first
    if SSOT_FILE.exists():
        try:
            data = json.loads(SSOT_FILE.read_text())
            if data.get("tips"):
                return data
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback to legacy tips file
    if TIPS_FILE.exists():
        try:
            data = json.loads(TIPS_FILE.read_text())
            if data.get("tips"):
                return data
        except (json.JSONDecodeError, OSError):
            pass

    return None


def is_tips_fresh(tips_data: dict) -> bool:
    """Check if tips are recent enough to be relevant."""
    # Check both timestamp (legacy) and ended_at (SSOT)
    timestamp_str = tips_data.get("timestamp") or tips_data.get("ended_at")
    if not timestamp_str:
        return False

    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        age = datetime.now() - timestamp
        return age < timedelta(hours=MAX_TIPS_AGE_HOURS)
    except (ValueError, TypeError):
        return False


def notify_user(message: str) -> None:
    """Print to stderr so user sees the notification."""
    print(message, file=sys.stderr)


def format_tips_for_injection(tips_data: dict) -> tuple[str, str]:
    """Format tips for context injection. Returns (context_text, user_notification)."""
    tips = tips_data.get("tips", [])
    if not tips:
        return "", ""

    lines = []
    lines.append("[Previous Session Tips]")

    # Add summary if available
    summary = tips_data.get("summary", {})
    if summary:
        duration = summary.get("duration_min", 0)
        tool_calls = summary.get("tool_calls", 0)
        errors = summary.get("errors", 0)
        lines.append(f"Session: {duration:.0f}min, {tool_calls} calls, {errors} errors")

    # Format each tip for context
    for i, tip in enumerate(tips[:3], 1):  # Max 3 tips for context efficiency
        confidence = tip.get("confidence", 0)
        message = tip.get("message", "")
        command = tip.get("command", "")

        conf_pct = int(confidence * 100) if confidence < 1 else confidence
        lines.append(f"{i}. [{conf_pct}%] {message} -> {command}")

    context_text = " | ".join(lines)

    # User notification (shorter)
    tip_commands = [t.get("command", "") for t in tips[:3]]
    user_notification = f"[Tips Injected] {len(tips)} suggestions: {', '.join(tip_commands)}"

    return context_text, user_notification


def debug_log(msg: str) -> None:
    """Debug logging to stderr."""
    if "--debug" in sys.argv:
        print(f"[tips-auto-inject] {msg}", file=sys.stderr)


def main():
    try:
        json.load(sys.stdin)  # Consume stdin (hook protocol)
    except json.JSONDecodeError:
        debug_log("Failed to parse stdin JSON")
        print(json.dumps({}))
        sys.exit(0)

    # Get current session ID
    session_id = get_session_id()
    debug_log(f"Session ID: {session_id}")
    if not session_id:
        # No session yet, skip
        print(json.dumps({}))
        sys.exit(0)

    # Check if already injected this session
    if was_already_injected(session_id):
        debug_log("Tips already injected this session")
        print(json.dumps({}))
        sys.exit(0)

    # Load tips
    tips_data = load_tips()
    debug_log(f"Tips data loaded: {bool(tips_data)}")
    if not tips_data:
        debug_log("No tips data found")
        mark_injected(session_id)
        print(json.dumps({}))
        sys.exit(0)

    # Check freshness
    if not is_tips_fresh(tips_data):
        debug_log("Tips are stale (>24h)")
        mark_injected(session_id)
        print(json.dumps({}))
        sys.exit(0)

    # Skip if tips are from the same session
    tips_session = tips_data.get("session_id", "")
    debug_log(f"Tips session: {tips_session}, current: {session_id}")
    if tips_session == session_id:
        debug_log("Tips are from current session, skipping")
        mark_injected(session_id)
        print(json.dumps({}))
        sys.exit(0)

    # Format and inject
    context_text, user_notification = format_tips_for_injection(tips_data)
    if not context_text:
        mark_injected(session_id)
        print(json.dumps({}))
        sys.exit(0)

    # Mark as injected
    mark_injected(session_id)

    # Notify user via stderr (visible to user)
    notify_user(user_notification)

    # Output for context injection (visible to Claude)
    # Use simple format like ci_status_injector.py
    output = {"additionalContext": context_text}

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
