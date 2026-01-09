#!/usr/bin/env python3
"""
Metrics Log Rotation & Cleanup

Removes entries older than retention period from JSONL files.
Can be run manually or via cron.

Usage:
    python metrics-cleanup.py [--days 30] [--dry-run]
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"

JSONL_FILES = [
    "daily.jsonl",
    "tdd_compliance.jsonl",
    "prompt_optimization.jsonl",
]


def cleanup_jsonl(file_path: Path, cutoff: datetime, dry_run: bool = False) -> dict:
    """Remove entries older than cutoff from JSONL file."""
    if not file_path.exists():
        return {"file": file_path.name, "status": "not_found"}

    kept = []
    removed = 0

    with open(file_path) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                ts = entry.get("timestamp", "")
                if ts:
                    entry_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if entry_date.replace(tzinfo=None) > cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                else:
                    kept.append(line)  # Keep entries without timestamp
            except (json.JSONDecodeError, ValueError):
                kept.append(line)  # Keep malformed entries

    if not dry_run and removed > 0:
        with open(file_path, "w") as f:
            f.writelines(kept)

    return {
        "file": file_path.name,
        "kept": len(kept),
        "removed": removed,
        "dry_run": dry_run,
    }


def cleanup_session_state():
    """Reset session state if older than 24h."""
    session_file = METRICS_DIR / "session_state.json"
    if not session_file.exists():
        return {"file": "session_state.json", "status": "not_found"}

    try:
        data = json.loads(session_file.read_text())
        start_time = data.get("start_time", "")
        if start_time:
            session_start = datetime.fromisoformat(start_time)
            age_hours = (datetime.now() - session_start).total_seconds() / 3600
            if age_hours > 24:
                session_file.unlink()
                return {"file": "session_state.json", "status": "reset", "age_hours": age_hours}
        return {"file": "session_state.json", "status": "kept", "age_hours": age_hours}
    except (json.JSONDecodeError, OSError):
        return {"file": "session_state.json", "status": "error"}


def cleanup_suggestion_cache():
    """Remove stale suggestion cache."""
    cache_file = METRICS_DIR / "last_suggestion.json"
    if cache_file.exists():
        cache_file.unlink()
        return {"file": "last_suggestion.json", "status": "removed"}
    return {"file": "last_suggestion.json", "status": "not_found"}


def main():
    parser = argparse.ArgumentParser(description="Cleanup old metrics logs")
    parser.add_argument("--days", type=int, default=30, help="Retention period in days")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    args = parser.parse_args()

    cutoff = datetime.now() - timedelta(days=args.days)
    print(f"Cleaning up metrics older than {args.days} days (before {cutoff.date()})")
    print(f"Dry run: {args.dry_run}\n")

    results = []

    # Cleanup JSONL files
    for filename in JSONL_FILES:
        result = cleanup_jsonl(METRICS_DIR / filename, cutoff, args.dry_run)
        results.append(result)
        status = f"removed {result.get('removed', 0)}, kept {result.get('kept', 0)}"
        print(f"  {filename}: {status}")

    # Cleanup session state
    result = cleanup_session_state()
    results.append(result)
    print(f"  session_state.json: {result.get('status', 'unknown')}")

    # Cleanup suggestion cache
    result = cleanup_suggestion_cache()
    results.append(result)
    print(f"  last_suggestion.json: {result.get('status', 'unknown')}")

    total_removed = sum(r.get("removed", 0) for r in results)
    print(f"\nTotal entries removed: {total_removed}")

    if args.dry_run:
        print("\n(Dry run - no changes made)")


if __name__ == "__main__":
    main()
