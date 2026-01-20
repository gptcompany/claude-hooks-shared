#!/usr/bin/env python3
"""Session Restore Check Hook - Verifica sessioni interrotte.

Questo hook viene eseguito all'inizio di ogni prompt utente e:
1. Verifica se esiste una sessione precedente interrotta
2. Se trovata, suggerisce il recovery nel context

Hook type: UserPromptSubmit
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.mcp_client import (
        get_project_name,
        get_timestamp,
        memory_retrieve,
    )
except ImportError:
    # Fallback if import fails - use direct file access
    import json as _json

    def get_project_name():
        return Path.cwd().name

    def get_timestamp():
        return datetime.now(timezone.utc).isoformat()

    def memory_retrieve(key, namespace=""):
        # Direct read from MCP store file
        store_file = Path.home() / ".claude-flow" / "memory" / "store.json"
        full_key = f"{namespace}:{key}" if namespace else key

        try:
            if store_file.exists():
                with open(store_file) as f:
                    store = _json.load(f)
                if full_key in store.get("entries", {}):
                    return store["entries"][full_key].get("value")
        except Exception:
            pass
        return None


# Logging
LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "session_restore.log"

# State file to track if we already notified this session
NOTIFIED_FILE = LOG_DIR / "session_restore_notified.json"


def log(msg: str):
    """Log message to file."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{get_timestamp()} - {msg}\n")
    except Exception:
        pass


def already_notified(session_id: str) -> bool:
    """Check if we already notified about this session."""
    try:
        if NOTIFIED_FILE.exists():
            with open(NOTIFIED_FILE) as f:
                data = json.load(f)
                return session_id in data.get("notified", [])
    except Exception:
        pass
    return False


def mark_notified(session_id: str):
    """Mark session as notified."""
    try:
        data = {"notified": []}
        if NOTIFIED_FILE.exists():
            with open(NOTIFIED_FILE) as f:
                data = json.load(f)

        if "notified" not in data:
            data["notified"] = []

        data["notified"].append(session_id)
        # Keep only last 10
        data["notified"] = data["notified"][-10:]

        with open(NOTIFIED_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def was_interrupted(last_session: dict) -> bool:
    """Check if last session was interrupted (not completed normally)."""
    if not last_session:
        return False

    # If marked as completed, it wasn't interrupted
    if last_session.get("completed"):
        return False

    # Check timestamp - if very recent (< 5 min), might be same session
    try:
        ts = last_session.get("timestamp", "")
        if ts:
            last_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if (now - last_time) < timedelta(minutes=5):
                return False  # Too recent, probably same session
    except Exception:
        pass

    return True


def is_same_project(last_session: dict, current_project: str) -> bool:
    """Check if last session is for the same project."""
    return last_session.get("project") == current_project


def main():
    """Main hook execution."""
    try:
        # Read hook input
        hook_input = {}
        if not sys.stdin.isatty():
            try:
                hook_input = json.load(sys.stdin)
            except json.JSONDecodeError:
                pass

        project = get_project_name()
        log(f"Checking for interrupted sessions for project: {project}")

        # Get last session info
        last_session = memory_retrieve(f"session:{project}:last")

        if not last_session:
            log("No previous session found")
            print(json.dumps({}))
            return 0

        log(f"Found last session: {last_session}")

        # Check if it was interrupted
        if not was_interrupted(last_session):
            log("Last session completed normally")
            print(json.dumps({}))
            return 0

        # Check if same project
        if not is_same_project(last_session, project):
            log("Last session is for different project")
            print(json.dumps({}))
            return 0

        session_id = last_session.get("session_id", "unknown")

        # Check if we already notified
        if already_notified(session_id):
            log("Already notified about this session")
            print(json.dumps({}))
            return 0

        # Mark as notified
        mark_notified(session_id)

        # Build recovery message
        timestamp = last_session.get("timestamp", "unknown")
        cwd = last_session.get("cwd", "unknown")

        context = (
            f"[Session Recovery] Previous session '{session_id}' was interrupted. "
            f"Last activity: {timestamp}. "
            f"Directory: {cwd}. "
            f"Use `mcp__claude-flow__session_restore(name='{session_id}')` to restore context."
        )

        log(f"Injecting recovery context: {context}")

        result = {"additionalContext": context}
        print(json.dumps(result))
        return 0

    except Exception as e:
        log(f"Error: {e}")
        print(json.dumps({}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
