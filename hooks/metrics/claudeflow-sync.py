#!/usr/bin/env python3
"""
ClaudeFlow JSON + SQLite to QuestDB Sync Hook

Reads learning data from:
1. SQLite: ~/.claude/hive-mind/hive-mind.db (primary, full schema)
2. JSON fallback: .claude-flow/*.json (per-repo)

Syncs to QuestDB for time-series analysis.
Triggered on Stop hook to capture session learnings.

Tables written:
- claude_strategy_metrics: Strategy performance (conservative, balanced, aggressive)
- claude_strategy_trends: Score trend data per strategy
- claude_agent_learning: Per-agent learning patterns
- claude_neural_patterns: Neural patterns from SQLite
- claude_swarm_metrics: Swarm performance from SQLite
"""

import json
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

QUESTDB_HOST = "localhost"
QUESTDB_PORT = 9009

# Global SQLite database
GLOBAL_DB = Path.home() / ".claude" / "hive-mind" / "hive-mind.db"

# Repos with potential .claude-flow/ directories
REPOS = {
    "/media/sam/1TB/nautilus_dev": "nautilus",
    "/media/sam/1TB/UTXOracle": "utxoracle",
    "/media/sam/1TB/claude-flow": "claudeflow",
    "/media/sam/1TB/LiquidationHeatmap": "liquidation",
    "/media/sam/1TB/N8N_dev": "n8n",
}


def escape_tag(value: str) -> str:
    """Escape special characters in ILP tag values."""
    return str(value).replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def send_to_questdb(lines: list[str]) -> int:
    """Send ILP lines to QuestDB."""
    if not lines:
        return 0

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((QUESTDB_HOST, QUESTDB_PORT))
            for line in lines:
                s.sendall((line + "\n").encode())
        return len(lines)
    except Exception as e:
        print(f"QuestDB send error: {e}", file=sys.stderr)
        return 0


def sync_sqlite_data() -> list[str]:
    """Sync data from global SQLite database."""
    lines = []

    if not GLOBAL_DB.exists():
        return lines

    try:
        conn = sqlite3.connect(str(GLOBAL_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        ts_now = int(datetime.utcnow().timestamp() * 1e9)

        # Sync neural_patterns
        cursor.execute("""
            SELECT swarm_id, pattern_type, confidence, usage_count, success_rate,
                   created_at, last_used_at
            FROM neural_patterns
            ORDER BY last_used_at DESC LIMIT 50
        """)
        for row in cursor.fetchall():
            swarm_id = escape_tag(row["swarm_id"] or "global")
            pattern_type = escape_tag(row["pattern_type"] or "unknown")
            lines.append(
                f"claude_neural_patterns,"
                f"swarm_id={swarm_id},"
                f"pattern_type={pattern_type} "
                f"confidence={row['confidence'] or 0},"
                f"usage_count={row['usage_count'] or 0}i,"
                f"success_rate={row['success_rate'] or 0} "
                f"{ts_now}"
            )

        # Sync performance_metrics
        cursor.execute("""
            SELECT swarm_id, agent_id, metric_type, metric_value, timestamp
            FROM performance_metrics
            ORDER BY timestamp DESC LIMIT 100
        """)
        for row in cursor.fetchall():
            swarm_id = escape_tag(row["swarm_id"] or "global")
            agent_id = escape_tag(row["agent_id"] or "system")
            metric_type = escape_tag(row["metric_type"] or "unknown")
            lines.append(
                f"claude_swarm_metrics,"
                f"swarm_id={swarm_id},"
                f"agent_id={agent_id},"
                f"metric_type={metric_type} "
                f"value={row['metric_value'] or 0} "
                f"{ts_now}"
            )

        # Sync session_history
        cursor.execute("""
            SELECT swarm_id, tasks_completed, tasks_failed, total_messages,
                   avg_task_duration, started_at
            FROM session_history
            ORDER BY started_at DESC LIMIT 20
        """)
        for row in cursor.fetchall():
            swarm_id = escape_tag(row["swarm_id"] or "global")
            lines.append(
                f"claude_session_history,"
                f"swarm_id={swarm_id} "
                f"tasks_completed={row['tasks_completed'] or 0}i,"
                f"tasks_failed={row['tasks_failed'] or 0}i,"
                f"total_messages={row['total_messages'] or 0}i,"
                f"avg_task_duration={row['avg_task_duration'] or 0} "
                f"{ts_now}"
            )

        conn.close()
    except Exception as e:
        print(f"SQLite sync error: {e}", file=sys.stderr)

    return lines


def sync_agents_profiles(repo_path: Path, repo_name: str) -> list[str]:
    """Sync agents-profiles.json (strategy performance)."""
    lines = []
    profiles_file = repo_path / ".claude-flow" / "agents-profiles.json"

    if not profiles_file.exists():
        return lines

    try:
        data = json.loads(profiles_file.read_text())
        ts_now = int(datetime.utcnow().timestamp() * 1e9)

        for strategy, metrics in data.items():
            if not isinstance(metrics, dict):
                continue

            # Strategy metrics
            success_rate = metrics.get("successRate", 0)
            avg_score = metrics.get("avgScore", 0)
            avg_exec = metrics.get("avgExecutionTime", 0)
            uses = metrics.get("uses", 0)
            real_exec = metrics.get("realExecutions", 0)
            improving = "t" if metrics.get("improving", False) else "f"

            # Parse improvement rate (comes as string like "-19.1")
            imp_rate_str = metrics.get("improvementRate", "0")
            try:
                imp_rate = float(imp_rate_str)
            except (ValueError, TypeError):
                imp_rate = 0.0

            lines.append(
                f"claude_strategy_metrics,"
                f"project={escape_tag(repo_name)},"
                f"strategy={escape_tag(strategy)} "
                f"success_rate={success_rate},"
                f"avg_score={avg_score},"
                f"avg_execution_time={avg_exec},"
                f"uses={uses}i,"
                f"real_executions={real_exec}i,"
                f"improving={improving},"
                f"improvement_rate={imp_rate} "
                f"{ts_now}"
            )

            # Trend data (last 5 entries to avoid flooding)
            trend = metrics.get("trend", [])[-5:]
            for entry in trend:
                score = entry.get("score", 0)
                is_real = "t" if entry.get("real", False) else "f"

                # Parse timestamp from trend
                ts_str = entry.get("timestamp", "")
                try:
                    ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts_ns = int(ts_dt.timestamp() * 1e9)
                except Exception:
                    ts_ns = ts_now

                lines.append(
                    f"claude_strategy_trends,"
                    f"project={escape_tag(repo_name)},"
                    f"strategy={escape_tag(strategy)} "
                    f"score={score},"
                    f"is_real={is_real} "
                    f"{ts_ns}"
                )

    except Exception as e:
        print(f"Error parsing {profiles_file}: {e}", file=sys.stderr)

    return lines


def sync_agent_models(repo_path: Path, repo_name: str) -> list[str]:
    """Sync models/*.json (per-agent learning)."""
    lines = []
    models_dir = repo_path / ".claude-flow" / "models"

    if not models_dir.exists():
        return lines

    ts_now = int(datetime.utcnow().timestamp() * 1e9)

    for model_file in models_dir.glob("*.json"):
        try:
            agent_type = model_file.stem.replace("agent-", "").replace("-model", "")
            data = json.loads(model_file.read_text())

            # Get latest score from history
            score_history = data.get("scoreHistory", [])
            if score_history:
                latest = score_history[-1]
                score = latest.get("score", 0)
                passed = "t" if latest.get("passed", False) else "f"

                lines.append(
                    f"claude_agent_learning,"
                    f"project={escape_tag(repo_name)},"
                    f"agent_type={escape_tag(agent_type)},"
                    f"pattern_type=score "
                    f"score={score},"
                    f"passed={passed} "
                    f"{ts_now}"
                )

            # Patterns if available
            patterns = data.get("patterns", {})
            for pattern_name, pattern_data in patterns.items():
                if isinstance(pattern_data, dict):
                    confidence = pattern_data.get("confidence", 0)

                    lines.append(
                        f"claude_agent_learning,"
                        f"project={escape_tag(repo_name)},"
                        f"agent_type={escape_tag(agent_type)},"
                        f"pattern_type={escape_tag(pattern_name)} "
                        f"score={confidence},"
                        f"passed=t "
                        f"{ts_now}"
                    )

        except Exception as e:
            print(f"Error parsing {model_file}: {e}", file=sys.stderr)

    return lines


def main():
    """Main sync function - called as Stop hook."""
    # Read hook input (not used for sync, but required for hook protocol)
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    all_lines = []
    synced_sources = []

    # 1. Sync from global SQLite (primary)
    sqlite_lines = sync_sqlite_data()
    if sqlite_lines:
        all_lines.extend(sqlite_lines)
        synced_sources.append("sqlite:global")

    # 2. Sync from per-repo JSON (fallback/additional)
    for repo_path_str, repo_name in REPOS.items():
        repo_path = Path(repo_path_str)
        cf_dir = repo_path / ".claude-flow"

        if not cf_dir.exists():
            continue

        lines = []
        lines.extend(sync_agents_profiles(repo_path, repo_name))
        lines.extend(sync_agent_models(repo_path, repo_name))

        if lines:
            all_lines.extend(lines)
            synced_sources.append(f"json:{repo_name}")

    # Send all to QuestDB
    sent = send_to_questdb(all_lines)

    # Output for hook protocol
    result = {
        "synced_sources": synced_sources,
        "lines_sent": sent,
        "sqlite_db": str(GLOBAL_DB) if GLOBAL_DB.exists() else None,
        "timestamp": datetime.utcnow().isoformat(),
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
