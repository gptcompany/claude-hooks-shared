#!/usr/bin/env python3
"""
ClaudeFlow Health Monitor Hook

Monitors ClaudeFlow health and logs metrics to QuestDB.
Triggered periodically or on specific events.

Usage:
    Registered as a hook for research-related events.
"""

import json
import os
import socket
import sys
from datetime import datetime
from pathlib import Path

QUESTDB_HOST = os.getenv("QUESTDB_HOST", "localhost")
QUESTDB_ILP_PORT = int(os.getenv("QUESTDB_ILP_PORT", 9009))
STATE_FILE = Path.home() / ".claude" / "metrics" / "claudeflow_circuit.json"


def get_circuit_state():
    """Read circuit breaker state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "state": "closed",
        "failure_count": 0,
        "total_calls": 0,
        "total_failures": 0,
        "total_fallbacks": 0,
    }


def log_health_metric(state: dict) -> bool:
    """Log health metric to QuestDB."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((QUESTDB_HOST, QUESTDB_ILP_PORT))
        sock.settimeout(2.0)

        # Build ILP line
        circuit_state = state.get("state", "unknown").replace(" ", "\\ ")
        fields = (
            f'state="{circuit_state}",'
            f"failure_count={state.get('failure_count', 0)}i,"
            f"total_calls={state.get('total_calls', 0)}i,"
            f"total_failures={state.get('total_failures', 0)}i,"
            f"total_fallbacks={state.get('total_fallbacks', 0)}i"
        )
        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = f"claudeflow_health {fields} {timestamp_ns}\n"

        sock.sendall(line.encode())
        sock.close()
        return True

    except OSError:
        return False


def main():
    """Main hook entry point."""
    # Read circuit state
    state = get_circuit_state()

    # Log to QuestDB
    logged = log_health_metric(state)

    # Output for hook system
    result = {
        "healthy": state.get("state") == "closed",
        "state": state.get("state"),
        "failure_count": state.get("failure_count", 0),
        "logged_to_questdb": logged,
    }

    print(json.dumps(result))

    # Exit code based on health
    sys.exit(0 if result["healthy"] else 1)


if __name__ == "__main__":
    main()
