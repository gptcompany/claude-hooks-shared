#!/usr/bin/env python3
"""Session Checkpoint Hook - Salva sessione automaticamente su Stop.

Questo hook viene eseguito alla fine di ogni sessione Claude e:
1. Salva lo stato della sessione in claude-flow
2. Memorizza il riferimento all'ultima sessione per recovery
3. Sincronizza con QuestDB per metriche

Hook type: Stop
"""

import contextlib
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
        session_save,
    )
except ImportError:
    # Fallback if import fails - use direct file access
    def get_project_name():
        return Path.cwd().name

    def get_timestamp():
        return datetime.now(timezone.utc).isoformat()

    def session_save(name, include_memory=True):
        # Skip session_save in fallback - not critical
        return {"success": False, "fallback": True}

    def memory_store(key, value, namespace=""):
        # Direct write to MCP store file
        import json

        store_file = Path.home() / ".claude-flow" / "memory" / "store.json"
        store_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            if store_file.exists():
                with open(store_file) as f:
                    store = json.load(f)
            else:
                store = {"entries": {}}

            full_key = f"{namespace}:{key}" if namespace else key
            now = datetime.now(timezone.utc).isoformat()

            store["entries"][full_key] = {
                "key": full_key,
                "value": value,
                "metadata": {},
                "storedAt": now,
                "accessCount": 0,
                "lastAccessed": now,
            }

            with open(store_file, "w") as f:
                json.dump(store, f, indent=2)

            return {"success": True, "fallback": True}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Logging
LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "session_checkpoint.log"


def log(msg: str):
    """Log message to file."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{get_timestamp()} - {msg}\n")
    except Exception:
        pass


def get_session_metrics() -> dict:
    """Collect session metrics from environment/files."""
    metrics = {
        "cwd": os.getcwd(),
        "project": get_project_name(),
        "timestamp": get_timestamp(),
    }

    # Try to get metrics from environment
    if metrics_file := os.environ.get("CLAUDE_METRICS_FILE"):
        try:
            with open(metrics_file) as f:
                metrics["session_metrics"] = json.load(f)
        except Exception:
            pass

    # Try to get conversation stats
    conv_file = LOG_DIR / "conversation_stats.json"
    if conv_file.exists():
        try:
            with open(conv_file) as f:
                metrics["conversation"] = json.load(f)
        except Exception:
            pass

    return metrics


def main():
    """Main hook execution."""
    try:
        # Read hook input
        hook_input = {}
        if not sys.stdin.isatty():
            with contextlib.suppress(json.JSONDecodeError):
                hook_input = json.load(sys.stdin)

        project = get_project_name()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        session_id = f"{project}-{timestamp}"

        log(f"Creating checkpoint: {session_id}")

        # Collect metrics
        metrics = get_session_metrics()
        metrics["hook_input"] = hook_input
        metrics["session_id"] = session_id

        # 1. Save session to claude-flow
        save_result = session_save(session_id, include_memory=True)
        log(f"Session save result: {save_result}")

        # 2. Store reference to last session for recovery
        memory_result = memory_store(
            key=f"session:{project}:last",
            value={
                "session_id": session_id,
                "timestamp": get_timestamp(),
                "project": project,
                "cwd": os.getcwd(),
                "completed": True,  # Mark as completed (not interrupted)
            },
        )
        log(f"Memory store result: {memory_result}")

        # 3. Store session metrics
        memory_store(key=f"session:{project}:metrics:{timestamp}", value=metrics)

        # Output result (no output needed for Stop hook)
        result = {
            "checkpoint_created": True,
            "session_id": session_id,
            "project": project,
        }

        log(f"Checkpoint complete: {result}")

        # Don't output anything - Stop hooks shouldn't modify response
        return 0

    except Exception as e:
        log(f"Error: {e}")
        # Don't fail the hook - just log and continue
        return 0


if __name__ == "__main__":
    sys.exit(main())
