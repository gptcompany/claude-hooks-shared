#!/usr/bin/env python3
"""
Export Claude Code Metrics to QuestDB

Reads metrics from JSONL files and exports to QuestDB via ILP protocol.
Replaces InfluxDB export - consolidated on single time-series DB.

Usage:
    python metrics-export-questdb.py [--days 7] [--dry-run] [--quiet]

Environment:
    QUESTDB_HOST: QuestDB host (default: localhost)
    QUESTDB_ILP_PORT: QuestDB ILP port (default: 9009)
"""

import argparse
import json
import os
import socket
from datetime import datetime, timedelta
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"
STATS_DIR = Path.home() / ".claude" / "stats"

# QuestDB config
QUESTDB_HOST = os.environ.get("QUESTDB_HOST", "localhost")
QUESTDB_ILP_PORT = int(os.environ.get("QUESTDB_ILP_PORT", "9009"))


def load_jsonl(file_path: Path, cutoff: datetime) -> list[dict]:
    """Load JSONL entries after cutoff date."""
    if not file_path.exists():
        return []

    entries = []
    with open(file_path) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                ts = entry.get("timestamp", "")
                if ts:
                    entry_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if entry_date.replace(tzinfo=None) > cutoff:
                        entries.append(entry)
            except (json.JSONDecodeError, ValueError):
                continue
    return entries


def to_ilp(table: str, tags: dict, fields: dict, timestamp: str) -> str:
    """Convert to QuestDB ILP (InfluxDB Line Protocol)."""
    # Format tags
    tag_str = ",".join(f"{k}={v}" for k, v in tags.items() if v)

    # Format fields
    field_parts = []
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, bool):
            field_parts.append(f"{k}={'t' if v else 'f'}")
        elif isinstance(v, int):
            field_parts.append(f"{k}={v}i")
        elif isinstance(v, float):
            field_parts.append(f"{k}={v}")
        elif isinstance(v, str):
            # Escape quotes in strings
            v_escaped = v.replace('"', '\\"')
            field_parts.append(f'{k}="{v_escaped}"')

    if not field_parts:
        return ""

    field_str = ",".join(field_parts)

    # Format timestamp (nanoseconds)
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        ts_ns = int(dt.timestamp() * 1e9)
    except ValueError:
        ts_ns = int(datetime.now().timestamp() * 1e9)

    if tag_str:
        return f"{table},{tag_str} {field_str} {ts_ns}"
    return f"{table} {field_str} {ts_ns}"


def convert_session_metrics(entries: list[dict]) -> list[str]:
    """Convert session_metrics.jsonl entries."""
    lines = []

    for entry in entries:
        timestamp = entry.get("timestamp", "")
        project = entry.get("project", "unknown").replace(" ", "_")
        session_id = entry.get("session_id", "unknown")

        tags = {"project": project, "session_id": session_id}

        # Session end event
        if "duration_seconds" in entry:
            fields = {
                "duration_seconds": entry.get("duration_seconds", 0),
                "tool_calls": entry.get("tool_calls", 0),
                "errors": entry.get("errors", 0),
                "tasks_completed": entry.get("tasks_completed", 0),
            }
            line = to_ilp("claude_sessions", tags, fields, timestamp)
            if line:
                lines.append(line)

    return lines


def convert_daily_metrics(entries: list[dict]) -> list[str]:
    """Convert daily.jsonl entries."""
    lines = []

    for entry in entries:
        entry_type = entry.get("type", "")
        timestamp = entry.get("timestamp", "")
        project = entry.get("project", "unknown").replace(" ", "_")
        session_id = entry.get("session_id", "unknown")

        tags = {"project": project, "session_id": session_id}

        if entry_type == "file_edit":
            fields = {"is_rework": entry.get("is_rework", False)}
            line = to_ilp("claude_file_edits", tags, fields, timestamp)

        elif entry_type == "test_run":
            fields = {"passed": entry.get("passed", False)}
            line = to_ilp("claude_test_runs", tags, fields, timestamp)

        elif entry_type == "agent_spawn":
            tags["agent_type"] = entry.get("agent_type", "unknown")
            fields = {"success": entry.get("success", True)}
            line = to_ilp("claude_agents", tags, fields, timestamp)

        elif entry_type == "cycle_time":
            fields = {
                "seconds": entry.get("cycle_time_seconds", 0.0),
                "minutes": entry.get("cycle_time_minutes", 0.0),
                "iterations": entry.get("iterations", 0),
            }
            line = to_ilp("claude_cycle_times", tags, fields, timestamp)

        elif entry_type == "session_stats":
            fields = {
                "tool_calls": entry.get("tool_calls", 0),
                "errors": entry.get("errors", 0),
                "error_rate": entry.get("error_rate", 0.0),
            }
            line = to_ilp("claude_sessions", tags, fields, timestamp)

        else:
            continue

        if line:
            lines.append(line)

    return lines


def convert_tdd_metrics(entries: list[dict]) -> list[str]:
    """Convert TDD compliance entries."""
    lines = []

    for entry in entries:
        entry_type = entry.get("type", "")
        timestamp = entry.get("timestamp", "")
        project = entry.get("project", "unknown").replace(" ", "_")

        file_name = ""
        if entry_type == "violation":
            file_name = Path(entry.get("file", "")).name[:50]

        tags = {"project": project, "event_type": entry_type}
        if file_name:
            tags["file_name"] = file_name

        fields = {"count": 1}
        line = to_ilp("claude_tdd", tags, fields, timestamp)
        if line:
            lines.append(line)

    return lines


def convert_prompt_metrics(entries: list[dict]) -> list[str]:
    """Convert prompt optimization entries."""
    lines = []

    for entry in entries:
        entry_type = entry.get("type", "")
        timestamp = entry.get("timestamp", "")

        tags = {"event_type": entry_type}
        fields = {}

        if entry_type == "optimized":
            tags["target_model"] = entry.get("target_model", "unknown")
            tags["optimizer_model"] = entry.get("optimizer_model", "unknown")
            tags["style"] = entry.get("style", "unknown")
            fields = {
                "ambiguity": entry.get("ambiguity_score", 0.0),
                "confidence": entry.get("confidence", 0.0),
                "expansion_ratio": entry.get("suggested_length", 1)
                / max(entry.get("original_length", 1), 1),
            }

        elif entry_type == "passthrough":
            tags["reason"] = entry.get("reason", "unknown")
            fields = {"count": 1}

        elif entry_type == "acceptance":
            fields = {
                "accepted": entry.get("accepted", False),
                "similarity": entry.get("similarity", 0.0),
            }

        else:
            continue

        line = to_ilp("claude_prompts", tags, fields, timestamp)
        if line:
            lines.append(line)

    return lines


def send_to_questdb(lines: list[str], dry_run: bool = False) -> dict:
    """Send ILP lines to QuestDB."""
    if dry_run:
        return {"status": "dry_run", "lines": len(lines)}

    if not lines:
        return {"status": "success", "lines": 0}

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((QUESTDB_HOST, QUESTDB_ILP_PORT))

        data = "\n".join(lines) + "\n"
        sock.sendall(data.encode())
        sock.close()

        return {"status": "success", "lines": len(lines)}

    except ConnectionRefusedError:
        return {
            "status": "error",
            "message": f"Cannot connect to QuestDB at {QUESTDB_HOST}:{QUESTDB_ILP_PORT}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def find_session_metrics_files() -> list[Path]:
    """Find all session_metrics.jsonl files."""
    files = set()

    # Global stats
    global_file = STATS_DIR / "session_metrics.jsonl"
    if global_file.exists():
        files.add(global_file)

    # Per-project stats
    projects_dir = Path.home() / ".claude" / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                stats_file = project_dir / "session_metrics.jsonl"
                if stats_file.exists():
                    files.add(stats_file)

    return list(files)


def main():
    parser = argparse.ArgumentParser(description="Export metrics to QuestDB")
    parser.add_argument("--days", type=int, default=7, help="Days of history to export")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually send data")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")

    args = parser.parse_args()
    cutoff = datetime.now() - timedelta(days=args.days)

    if not args.quiet:
        print(f"Exporting metrics from last {args.days} days to QuestDB")
        print(f"Host: {QUESTDB_HOST}:{QUESTDB_ILP_PORT}")

    all_lines = []

    # Session metrics
    for session_file in find_session_metrics_files():
        entries = load_jsonl(session_file, cutoff)
        all_lines.extend(convert_session_metrics(entries))
        if not args.quiet:
            print(f"  {session_file.name}: {len(entries)} entries")

    # Daily metrics
    daily_file = METRICS_DIR / "daily.jsonl"
    if daily_file.exists():
        entries = load_jsonl(daily_file, cutoff)
        all_lines.extend(convert_daily_metrics(entries))
        if not args.quiet:
            print(f"  daily.jsonl: {len(entries)} entries")

    # TDD metrics
    tdd_file = METRICS_DIR / "tdd_compliance.jsonl"
    if tdd_file.exists():
        entries = load_jsonl(tdd_file, cutoff)
        all_lines.extend(convert_tdd_metrics(entries))
        if not args.quiet:
            print(f"  tdd_compliance.jsonl: {len(entries)} entries")

    # Prompt metrics
    prompt_file = METRICS_DIR / "prompt_optimizer.jsonl"
    if prompt_file.exists():
        entries = load_jsonl(prompt_file, cutoff)
        all_lines.extend(convert_prompt_metrics(entries))
        if not args.quiet:
            print(f"  prompt_optimizer.jsonl: {len(entries)} entries")

    if not args.quiet:
        print(f"\nTotal lines: {len(all_lines)}")

    # Send to QuestDB
    result = send_to_questdb(all_lines, args.dry_run)

    if not args.quiet:
        print(f"Result: {result}")

    return 0 if result.get("status") in ("success", "dry_run") else 1


if __name__ == "__main__":
    exit(main())
