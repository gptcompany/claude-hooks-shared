#!/usr/bin/env python3
"""
QuestDB Client for Tips Engine v2

Provides:
- Historical stats queries with 3-tier fallback
- Similar situation lookup
- Command success rates
- Rule accuracy tracking
"""

import json
import os
import urllib.parse
import urllib.request

# Import from tips_engine
from tips_engine import (
    HistoricalStats,
    IndustryDefaults,
    MultiWindowStats,
    SessionMetrics,
    WindowStats,
)

# QuestDB configuration (from canonical.yaml)
QUESTDB_HOST = os.getenv("QUESTDB_HOST", "localhost")
QUESTDB_HTTP_PORT = int(os.getenv("QUESTDB_HTTP_PORT", 9000))
QUESTDB_URL = f"http://{QUESTDB_HOST}:{QUESTDB_HTTP_PORT}/exec"

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Cache settings
CACHE_TTL_SECONDS = 3600  # 1 hour cache for historical stats


def query_questdb(sql: str, timeout: float = 5.0) -> dict | None:
    """
    Execute SQL query against QuestDB REST API.

    Returns parsed JSON response or None on error.
    """
    try:
        params = urllib.parse.urlencode({"query": sql})
        url = f"{QUESTDB_URL}?{params}"

        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None


def get_historical_stats(project: str, days: int = 30) -> HistoricalStats:
    """
    Get historical stats with 3-tier fallback:
    1. Project-specific data (best)
    2. Cross-project data (same user, different projects)
    3. Industry defaults (DORA benchmarks)
    """
    # Try Redis cache first
    cached = _get_from_redis(f"historical_stats:{project}")
    if cached:
        return HistoricalStats(**cached)

    # Tier 1: Project-specific data
    project_stats = _query_project_stats(project, days)
    if project_stats and project_stats.session_count >= 5:
        _save_to_redis(f"historical_stats:{project}", _stats_to_dict(project_stats))
        return project_stats

    # Tier 2: Cross-project data
    cross_project_stats = _query_project_stats(None, days)  # All projects
    if cross_project_stats and cross_project_stats.session_count >= 10:
        result = cross_project_stats.with_lower_confidence(0.8)
        result.data_source = "cross_project"
        _save_to_redis(f"historical_stats:{project}", _stats_to_dict(result))
        return result

    # Tier 3: Industry defaults - cache to avoid repeated lookups
    defaults = IndustryDefaults.to_historical_stats()
    _save_to_redis(f"historical_stats:{project}", _stats_to_dict(defaults))
    return defaults


def _query_project_stats(project: str | None, days: int) -> HistoricalStats | None:
    """Query QuestDB for project statistics."""
    project_filter = f"AND project = '{project}'" if project else ""

    # Query session statistics
    session_sql = f"""
    SELECT
        COUNT(*) as session_count,
        AVG(error_rate) as avg_error_rate,
        STDDEV(error_rate) as stddev_error_rate,
        AVG(rework_rate) as avg_rework_rate,
        STDDEV(rework_rate) as stddev_rework_rate,
        AVG(test_pass_rate) as avg_test_pass_rate,
        STDDEV(test_pass_rate) as stddev_test_pass_rate
    FROM claude_sessions
    WHERE timestamp > dateadd('d', -{days}, now())
    {project_filter}
    """

    result = query_questdb(session_sql)
    if not result or not result.get("dataset"):
        return None

    row = result["dataset"][0] if result["dataset"] else None
    if not row or row[0] == 0:
        return None

    # Query command success rates
    cmd_sql = f"""
    SELECT
        tool_name,
        SUM(CASE WHEN success THEN 1 ELSE 0 END)::float / COUNT(*) as success_rate
    FROM claude_tool_usage
    WHERE timestamp > dateadd('d', -{days}, now())
    {project_filter}
    AND tool_name LIKE '/%'
    GROUP BY tool_name
    HAVING COUNT(*) >= 3
    """

    cmd_result = query_questdb(cmd_sql)
    command_rates = {}
    if cmd_result and cmd_result.get("dataset"):
        for cmd_row in cmd_result["dataset"]:
            command_rates[cmd_row[0]] = cmd_row[1]

    # Query rule accuracies
    rule_sql = f"""
    SELECT
        rule_name,
        SUM(CASE WHEN outcome = 'helpful' THEN 1 ELSE 0 END)::float / COUNT(*) as accuracy
    FROM claude_tip_outcomes
    WHERE timestamp > dateadd('d', -{days}, now())
    {project_filter}
    GROUP BY rule_name
    HAVING COUNT(*) >= 3
    """

    rule_result = query_questdb(rule_sql)
    rule_accuracies = {}
    if rule_result and rule_result.get("dataset"):
        for rule_row in rule_result["dataset"]:
            rule_accuracies[rule_row[0]] = rule_row[1]

    # Query returns all 7 columns (indices 0-6)
    # NULL values use industry defaults
    return HistoricalStats(
        session_count=int(row[0]) if row[0] else 0,
        data_source="project" if project else "cross_project",
        avg_error_rate=float(row[1]) if row[1] else 0.10,
        stddev_error_rate=float(row[2]) if row[2] else 0.05,
        avg_rework_rate=float(row[3]) if row[3] else 0.15,
        stddev_rework_rate=float(row[4]) if row[4] else 0.08,
        avg_test_pass_rate=float(row[5]) if row[5] else 0.85,
        stddev_test_pass_rate=float(row[6]) if row[6] else 0.10,
        command_success_rates=command_rates,
        rule_accuracies=rule_accuracies,
        confidence_penalty=0.0,
    )


def get_multi_window_stats(project: str) -> MultiWindowStats:
    """
    Analyze distribution across multiple session windows for trend analysis.

    Windows:
    - all_time: All available sessions (baseline)
    - recent: Last 50 sessions
    - trend: Last 20 sessions

    Returns MultiWindowStats with computed trends.
    """
    project_filter = f"WHERE project = '{project}'" if project else ""

    # Query total session count first
    count_sql = f"""
    SELECT COUNT(*) FROM claude_sessions {project_filter}
    """
    count_result = query_questdb(count_sql)
    total_sessions = 0
    if count_result and count_result.get("dataset"):
        total_sessions = int(count_result["dataset"][0][0] or 0)

    if total_sessions == 0:
        return MultiWindowStats(total_sessions=0, data_source="none")

    # Query stats for each window
    windows = {
        "all_time": total_sessions,  # All sessions
        "recent": min(50, total_sessions),  # Last 50
        "trend": min(20, total_sessions),  # Last 20
    }

    result = MultiWindowStats(
        total_sessions=total_sessions,
        data_source="project" if project else "cross_project",
    )

    for window_name, limit in windows.items():
        sql = f"""
        SELECT
            COUNT(*) as session_count,
            AVG(error_rate) as avg_error_rate,
            STDDEV(error_rate) as stddev_error_rate,
            AVG(rework_rate) as avg_rework_rate,
            STDDEV(rework_rate) as stddev_rework_rate
        FROM (
            SELECT error_rate, rework_rate
            FROM claude_sessions
            {project_filter}
            ORDER BY timestamp DESC
            LIMIT {limit}
        )
        """

        query_result = query_questdb(sql)
        if query_result and query_result.get("dataset"):
            row = query_result["dataset"][0]
            window_stats = WindowStats(
                session_count=int(row[0]) if row[0] else 0,
                avg_error_rate=float(row[1]) if row[1] else 0.0,
                stddev_error_rate=float(row[2]) if row[2] else 0.0,
                avg_rework_rate=float(row[3]) if row[3] else 0.0,
                stddev_rework_rate=float(row[4]) if row[4] else 0.0,
            )

            if window_name == "all_time":
                result.all_time = window_stats
            elif window_name == "recent":
                result.recent = window_stats
            elif window_name == "trend":
                result.trend = window_stats

    # Compute trends
    result.compute_trends()

    return result


def find_similar_situations(
    current: SessionMetrics,
    project: str,
    limit: int = 5,
) -> list[dict]:
    """
    Find past sessions with similar characteristics.
    Use their outcomes to inform current recommendations.
    """
    sql = f"""
    SELECT
        session_id,
        error_rate,
        rework_rate,
        test_pass_rate,
        outcome,
        ABS(error_rate - {current.error_rate}) + ABS(rework_rate - {current.rework_rate}) as distance
    FROM claude_sessions
    WHERE project = '{project}'
      AND timestamp > dateadd('d', -30, now())
      AND outcome IN ('success', 'partial')
    ORDER BY distance ASC
    LIMIT {limit}
    """

    result = query_questdb(sql)
    if not result or not result.get("dataset"):
        return []

    columns = result.get("columns", [])
    col_names = (
        [c["name"] for c in columns]
        if columns
        else ["session_id", "error_rate", "rework_rate", "test_pass_rate", "outcome", "distance"]
    )

    situations = []
    for row in result["dataset"]:
        situations.append(dict(zip(col_names, row)))

    return situations


def record_tip_outcome(
    tip_id: str,
    rule_name: str,
    command_suggested: str,
    outcome: str,
    project: str,
) -> bool:
    """
    Record tip outcome for learning.
    Outcome should be 'helpful', 'not_helpful', or 'ignored'.
    """
    # Use ILP protocol for insert
    from ilp_client import send_to_questdb_ilp

    data = {
        "tip_id": tip_id,
        "rule_name": rule_name,
        "command_suggested": command_suggested,
        "outcome": outcome,
        "project": project,
    }

    return send_to_questdb_ilp("claude_tip_outcomes", data)


# Redis helpers
def _get_redis_client():
    """Get Redis client with lazy initialization."""
    try:
        import redis

        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    except ImportError:
        return None
    except Exception:
        return None


def _get_from_redis(key: str) -> dict | None:
    """Get cached value from Redis."""
    client = _get_redis_client()
    if not client:
        return None

    try:
        data = client.get(key)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


def _save_to_redis(key: str, data: dict) -> bool:
    """Save value to Redis with TTL."""
    client = _get_redis_client()
    if not client:
        return False

    try:
        client.setex(key, CACHE_TTL_SECONDS, json.dumps(data))
        return True
    except Exception:
        return False


def _stats_to_dict(stats: HistoricalStats) -> dict:
    """Convert HistoricalStats to dict for caching."""
    return {
        "session_count": stats.session_count,
        "data_source": stats.data_source,
        "avg_error_rate": stats.avg_error_rate,
        "stddev_error_rate": stats.stddev_error_rate,
        "avg_rework_rate": stats.avg_rework_rate,
        "stddev_rework_rate": stats.stddev_rework_rate,
        "avg_test_pass_rate": stats.avg_test_pass_rate,
        "stddev_test_pass_rate": stats.stddev_test_pass_rate,
        "command_success_rates": stats.command_success_rates,
        "rule_accuracies": stats.rule_accuracies,
        "confidence_penalty": stats.confidence_penalty,
    }


def check_questdb_health() -> dict:
    """Check QuestDB connectivity and basic stats."""
    status = {
        "available": False,
        "latency_ms": None,
        "session_count": 0,
        "error": None,
    }

    try:
        import time

        start = time.time()

        result = query_questdb("SELECT COUNT(*) FROM claude_sessions", timeout=2.0)

        status["latency_ms"] = (time.time() - start) * 1000
        status["available"] = True

        if result and result.get("dataset"):
            status["session_count"] = result["dataset"][0][0]

    except Exception as e:
        status["error"] = str(e)

    return status


def check_redis_health() -> dict:
    """Check Redis connectivity."""
    status = {
        "available": False,
        "latency_ms": None,
        "error": None,
    }

    client = _get_redis_client()
    if not client:
        status["error"] = "Redis client not available"
        return status

    try:
        import time

        start = time.time()
        client.ping()
        status["latency_ms"] = (time.time() - start) * 1000
        status["available"] = True
    except Exception as e:
        status["error"] = str(e)

    return status


if __name__ == "__main__":
    # Health checks
    print("QuestDB Health:", check_questdb_health())
    print("Redis Health:", check_redis_health())

    # Test historical stats
    stats = get_historical_stats("claude-hooks-shared")
    print(f"\nHistorical Stats (source: {stats.data_source}):")
    print(f"  Sessions: {stats.session_count}")
    print(f"  Avg Error Rate: {stats.avg_error_rate:.2%}")
    print(f"  Avg Rework Rate: {stats.avg_rework_rate:.2%}")
