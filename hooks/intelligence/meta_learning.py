#!/usr/bin/env python3
"""Meta Learning Stop Hook - Extracts lessons from session data.

Analyzes session activity and extracts learning patterns:
- High rework: >3 edits on same file indicates iteration issues
- High error rate: >25% error rate indicates problems
- Quality drop: declining quality trend over session

Patterns are stored via mcp_client.pattern_store() for SONA learning.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.mcp_client import (
        get_project_name,
        get_timestamp,
        memory_retrieve,
        pattern_store,
    )
except ImportError:
    from datetime import datetime, timezone

    MCP_STORE = Path.home() / ".claude-flow" / "memory" / "store.json"

    def get_project_name() -> str:
        return Path.cwd().name

    def get_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load_store() -> dict:
        MCP_STORE.parent.mkdir(parents=True, exist_ok=True)
        if MCP_STORE.exists():
            with open(MCP_STORE) as f:
                return json.load(f)
        return {"entries": {}}

    def memory_retrieve(key: str, namespace: str = "") -> Any:
        store = _load_store()
        full_key = f"{namespace}:{key}" if namespace else key
        return store.get("entries", {}).get(full_key, {}).get("value")

    def pattern_store(
        _pattern: str,
        _pattern_type: str,
        _confidence: float,
        _metadata: dict | None = None,
    ) -> dict:
        """Fallback stub - args prefixed with _ to suppress unused warnings."""
        return {"success": True, "fallback": True}


LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "meta_learning.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SESSION_ANALYSIS_FILE = LOG_DIR / "session_analysis.json"

THRESHOLD_REWORK_EDITS = 3
THRESHOLD_ERROR_RATE = 0.25
THRESHOLD_QUALITY_DROP = 0.15
MIN_QUALITY_SAMPLES = 3


def load_trajectory_data(project: str) -> list[dict[str, Any]]:
    """Load trajectory index from memory."""
    try:
        data = memory_retrieve(f"trajectory:{project}:index")
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Failed to load trajectory data: {e}")
        return []


def load_session_analysis() -> dict[str, Any]:
    """Load session analyzer output from file."""
    try:
        if SESSION_ANALYSIS_FILE.exists():
            with open(SESSION_ANALYSIS_FILE) as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load session analysis: {e}")
    return {}


def load_file_edit_counts() -> dict[str, int]:
    """Load file edit counts from session metrics."""
    metrics_file = LOG_DIR / "file_edit_counts.json"
    try:
        if metrics_file.exists():
            with open(metrics_file) as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def load_quality_scores() -> list[float]:
    """Load quality scores from trajectory steps."""
    trajectory_index = load_trajectory_data(get_project_name())
    if not trajectory_index:
        return []

    scores = []
    for traj in trajectory_index[-10:]:
        if "success_rate" in traj:
            scores.append(traj["success_rate"])
        elif "success" in traj:
            scores.append(1.0 if traj["success"] else 0.5)
    return scores


def calculate_confidence(pattern_type: str, data: dict[str, Any]) -> float:
    """Calculate confidence score for a pattern based on signal strength.

    Base confidence is 0.5, with up to 0.5 additional based on severity.
    """
    base = 0.5
    bonus = 0.0

    if pattern_type == "high_rework":
        excess = data.get("edit_count", 0) - data.get(
            "threshold", THRESHOLD_REWORK_EDITS
        )
        bonus = min(0.5, excess * 0.15)
    elif pattern_type == "high_error":
        excess = data.get("error_rate", 0) - THRESHOLD_ERROR_RATE
        bonus = min(0.5, excess * 1.5)
    elif pattern_type == "quality_drop":
        excess = data.get("total_drop", 0) - data.get(
            "threshold", THRESHOLD_QUALITY_DROP
        )
        bonus = min(0.5, excess * 2)

    return min(1.0, max(0.0, base + bonus))


def extract_rework_pattern(file_edit_counts: dict[str, int]) -> dict[str, Any] | None:
    """Extract high rework pattern from file edit counts."""
    if not file_edit_counts:
        return None

    high_rework_files = [
        path
        for path, count in file_edit_counts.items()
        if count > THRESHOLD_REWORK_EDITS
    ]

    if not high_rework_files:
        return None

    max_edits = max(file_edit_counts[f] for f in high_rework_files)
    return {
        "type": "high_rework",
        "files": high_rework_files,
        "max_edits": max_edits,
        "confidence": calculate_confidence(
            "high_rework",
            {"edit_count": max_edits, "threshold": THRESHOLD_REWORK_EDITS},
        ),
    }


def extract_error_pattern(session_analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Extract high error rate pattern from session analysis."""
    session = session_analysis.get("session", {})
    if not session:
        return None

    error_rate = session.get("error_rate")
    if error_rate is None:
        tool_calls = session.get("tool_calls", 0)
        if tool_calls > 0:
            error_rate = session.get("errors", 0) / tool_calls
        else:
            return None

    if error_rate <= THRESHOLD_ERROR_RATE:
        return None

    return {
        "type": "high_error",
        "error_rate": error_rate,
        "total_errors": session.get("errors", 0),
        "confidence": calculate_confidence("high_error", {"error_rate": error_rate}),
    }


def extract_quality_drop_pattern(quality_scores: list[float]) -> dict[str, Any] | None:
    """Extract quality drop pattern from quality score trend."""
    if len(quality_scores) < MIN_QUALITY_SAMPLES:
        return None

    n = len(quality_scores)
    x_mean = (n - 1) / 2
    y_mean = sum(quality_scores) / n

    numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(quality_scores))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return None

    slope = numerator / denominator
    start_quality = quality_scores[0]
    end_quality = quality_scores[-1]
    total_change = start_quality - end_quality

    if total_change <= THRESHOLD_QUALITY_DROP or slope >= 0:
        return None

    return {
        "type": "quality_drop",
        "trend": "declining",
        "start_quality": start_quality,
        "end_quality": end_quality,
        "total_drop": total_change,
        "slope": slope,
        "confidence": calculate_confidence(
            "quality_drop",
            {"total_drop": total_change, "threshold": THRESHOLD_QUALITY_DROP},
        ),
    }


def extract_patterns(
    session_analysis: dict[str, Any],
    file_edit_counts: dict[str, int],
    quality_scores: list[float],
) -> list[dict[str, Any]]:
    """Extract all patterns from session data."""
    extractors = [
        (extract_rework_pattern, file_edit_counts),
        (extract_error_pattern, session_analysis),
        (extract_quality_drop_pattern, quality_scores),
    ]
    return [p for func, data in extractors if (p := func(data)) is not None]


def store_patterns(patterns: list[dict[str, Any]]) -> None:
    """Store extracted patterns via mcp_client."""
    project = get_project_name()
    timestamp = get_timestamp()

    for pattern in patterns:
        pattern_type = pattern.get("type", "unknown")
        confidence = pattern.get("confidence", 0.5)
        metadata = {
            "project": project,
            "timestamp": timestamp,
            **{k: v for k, v in pattern.items() if k not in ("type", "confidence")},
        }

        try:
            pattern_store(pattern_type, pattern_type, confidence, metadata)
            logger.info(f"Stored pattern: {pattern_type} (confidence={confidence:.2f})")
        except Exception as e:
            logger.error(f"Failed to store pattern {pattern_type}: {e}")


def main() -> int:
    """Main hook entry point. Returns 0 for graceful failure."""
    try:
        # Read stdin (required by hook protocol, but not used by this hook)
        if not sys.stdin.isatty():
            try:
                json.load(sys.stdin)  # Consume stdin
            except json.JSONDecodeError:
                pass

        project = get_project_name()
        trajectory_index = load_trajectory_data(project)
        session_analysis = load_session_analysis()
        file_edit_counts = load_file_edit_counts()
        quality_scores = load_quality_scores()

        logger.info(
            f"Loaded data: {len(trajectory_index)} trajectories, "
            f"{len(file_edit_counts)} file edits, {len(quality_scores)} quality scores"
        )

        patterns = extract_patterns(
            session_analysis=session_analysis,
            file_edit_counts=file_edit_counts,
            quality_scores=quality_scores,
        )

        logger.info(f"Extracted {len(patterns)} patterns")

        if patterns:
            store_patterns(patterns)

        print(json.dumps({}))
        return 0

    except Exception as e:
        logger.error(f"Error in meta_learning hook: {e}")
        print(json.dumps({}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
