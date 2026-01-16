#!/usr/bin/env python3
"""
Dead man's switch - alert if automation stops working.

Usage:
    # Record a heartbeat
    python heartbeat.py record <source>

    # Check if heartbeat is recent (exit 1 if stale)
    python heartbeat.py check

    # Show status
    python heartbeat.py status
"""

import json
import sys
from datetime import datetime
from pathlib import Path

HEARTBEAT_FILE = Path.home() / ".claude/heartbeat.json"
MAX_AGE_HOURS = 25  # Alert if no heartbeat in 25 hours


def record_heartbeat(source: str) -> None:
    """Record a heartbeat from a script."""
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "host": Path("/etc/hostname").read_text().strip() if Path("/etc/hostname").exists() else "unknown",
    }
    HEARTBEAT_FILE.write_text(json.dumps(data, indent=2))
    print(f"Heartbeat recorded from {source}")


def check_heartbeat() -> bool:
    """Check if heartbeat is recent. Returns False if stale."""
    if not HEARTBEAT_FILE.exists():
        return False

    try:
        data = json.loads(HEARTBEAT_FILE.read_text())
        last_beat = datetime.fromisoformat(data["timestamp"])
        age_hours = (datetime.utcnow() - last_beat).total_seconds() / 3600
        return age_hours < MAX_AGE_HOURS
    except (json.JSONDecodeError, KeyError, ValueError):
        return False


def get_status() -> dict:
    """Get detailed heartbeat status."""
    if not HEARTBEAT_FILE.exists():
        return {
            "exists": False,
            "healthy": False,
            "message": "No heartbeat file found",
        }

    try:
        data = json.loads(HEARTBEAT_FILE.read_text())
        last_beat = datetime.fromisoformat(data["timestamp"])
        age_hours = (datetime.utcnow() - last_beat).total_seconds() / 3600
        healthy = age_hours < MAX_AGE_HOURS

        return {
            "exists": True,
            "healthy": healthy,
            "last_beat": data["timestamp"],
            "source": data.get("source", "unknown"),
            "age_hours": round(age_hours, 2),
            "max_age_hours": MAX_AGE_HOURS,
            "message": "OK" if healthy else f"STALE - {age_hours:.1f}h old",
        }
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return {
            "exists": True,
            "healthy": False,
            "message": f"Invalid heartbeat file: {e}",
        }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "record":
        source = sys.argv[2] if len(sys.argv) > 2 else "manual"
        record_heartbeat(source)

    elif command == "check":
        if check_heartbeat():
            print("Heartbeat OK")
            sys.exit(0)
        else:
            print("ALERT: Heartbeat stale! Automation may have stopped.")
            sys.exit(1)

    elif command == "status":
        status = get_status()
        print(f"Heartbeat Status: {status['message']}")
        if status["exists"] and status.get("last_beat"):
            print(f"  Last beat: {status['last_beat']}")
            print(f"  Source: {status.get('source', 'unknown')}")
            print(f"  Age: {status.get('age_hours', 'N/A')} hours")
            print(f"  Max age: {status['max_age_hours']} hours")
        sys.exit(0 if status["healthy"] else 1)

    else:
        print(f"Unknown command: {command}")
        print("Valid commands: record, check, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
