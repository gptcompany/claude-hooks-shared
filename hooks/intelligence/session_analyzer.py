#!/usr/bin/env python3
"""
Intelligent Session Analyzer - Stop Hook

Analyzes session activity and git changes to provide stats for Claude's decision-making.
Outputs raw data only - Claude decides what action to take.

FAANG Standards:
- Full type hints
- Graceful error handling
- Structured logging
- No dead code
- Testable functions
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

# =============================================================================
# Configuration
# =============================================================================

METRICS_DIR = Path.home() / ".claude" / "metrics"
SESSION_STATE_FILE = METRICS_DIR / "session_state.json"
LAST_SESSION_STATS_FILE = METRICS_DIR / "last_session_stats.json"  # For next session
LOG_FILE = Path.home() / ".claude" / "logs" / "session-analyzer.log"

# Ensure log directory exists
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    handlers=[logging.FileHandler(LOG_FILE)],
)
logger = logging.getLogger(__name__)

# File patterns for categorization
CODE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".rs", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb", ".c", ".cpp", ".h"}
)
CONFIG_EXTENSIONS: frozenset[str] = frozenset({".json", ".yaml", ".yml", ".toml", ".ini", ".env"})
TEST_PATTERNS: tuple[str, ...] = ("test_", "_test.", "tests/", "spec.", ".spec.")


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class GitChanges:
    """Represents uncommitted git changes."""

    has_changes: bool = False
    lines_added: int = 0
    lines_deleted: int = 0
    code_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    other_files: list[str] = field(default_factory=list)


@dataclass
class SessionMetrics:
    """Represents session metrics."""

    tool_calls: int = 0
    errors: int = 0

    @property
    def error_rate(self) -> float:
        return self.errors / self.tool_calls if self.tool_calls > 0 else 0.0


# =============================================================================
# Git Analysis
# =============================================================================


def run_git_command(args: list[str], timeout: float = 5.0) -> str | None:
    """Run a git command and return stdout, or None on error."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Git command failed: {e}")
    return None


def categorize_file(filepath: str) -> str:
    """Categorize a file as code, test, config, or other."""
    filepath_lower = filepath.lower()
    filename = Path(filepath).name.lower()

    # Check for test files first (can be .py but should be categorized as test)
    if any(pattern in filepath_lower for pattern in TEST_PATTERNS):
        return "test"

    # Check extension (handles .env which has no suffix)
    ext = Path(filepath).suffix.lower()
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in CONFIG_EXTENSIONS or filename in {".env", ".envrc"}:
        return "config"
    return "other"


def get_uncommitted_changes() -> GitChanges:
    """Analyze uncommitted changes (staged + unstaged)."""
    changes = GitChanges()

    # Get changed file names
    diff_files = run_git_command(["diff", "--name-only", "HEAD"])
    staged_files = run_git_command(["diff", "--name-only", "--cached"])

    if diff_files is None and staged_files is None:
        return changes

    all_files: set[str] = set()
    if diff_files:
        all_files.update(diff_files.split("\n"))
    if staged_files:
        all_files.update(staged_files.split("\n"))
    all_files.discard("")

    if not all_files:
        return changes

    changes.has_changes = True

    # Categorize files
    for f in all_files:
        category = categorize_file(f)
        if category == "code":
            changes.code_files.append(f)
        elif category == "test":
            changes.test_files.append(f)
        elif category == "config":
            changes.config_files.append(f)
        else:
            changes.other_files.append(f)

    # Get line counts
    numstat = run_git_command(["diff", "--numstat", "HEAD"])
    if numstat:
        for line in numstat.split("\n"):
            if not line or "\t" not in line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                if parts[0].isdigit():
                    changes.lines_added += int(parts[0])
                if parts[1].isdigit():
                    changes.lines_deleted += int(parts[1])

    logger.info(f"Analyzed changes: +{changes.lines_added}/-{changes.lines_deleted}, {len(all_files)} files")
    return changes


def get_session_commits() -> list[dict[str, str]]:
    """Get commits made during this session (since start_commit)."""
    if not SESSION_STATE_FILE.exists():
        return []

    try:
        state = json.loads(SESSION_STATE_FILE.read_text())
        start_commit = state.get("start_commit")
        if not start_commit:
            return []

        log_output = run_git_command(["log", f"{start_commit}..HEAD", "--format=%H|%s", "--no-merges"])

        if not log_output:
            return []

        commits = []
        for line in log_output.split("\n"):
            if "|" in line:
                parts = line.split("|", 1)
                commits.append(
                    {
                        "hash": parts[0][:8],
                        "message": parts[1] if len(parts) > 1 else "",
                    }
                )
        return commits

    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to get session commits: {e}")
        return []


# =============================================================================
# Session Metrics
# =============================================================================


def parse_session_metrics(input_data: dict[str, Any]) -> SessionMetrics:
    """Parse session metrics from hook input."""
    session = input_data.get("session", {})
    return SessionMetrics(
        tool_calls=session.get("tool_calls", 0),
        errors=session.get("errors", 0),
    )


# =============================================================================
# Output Formatting
# =============================================================================


def format_session_stats(changes: GitChanges, metrics: SessionMetrics, commits: list[dict[str, str]]) -> str:
    """Format session stats - raw data only, Claude decides what to do."""
    parts: list[str] = []

    # Git changes - compact format
    if changes.has_changes:
        git_parts = [f"+{changes.lines_added}/-{changes.lines_deleted}"]
        if changes.code_files:
            git_parts.append(f"{len(changes.code_files)} code")
        if changes.test_files:
            git_parts.append(f"{len(changes.test_files)} test")
        if changes.config_files:
            git_parts.append(f"{len(changes.config_files)} config")
        parts.append(f"[uncommitted: {', '.join(git_parts)}]")

    # Session metrics
    if metrics.tool_calls > 0:
        parts.append(f"[session: {metrics.tool_calls} calls, {metrics.errors} errors]")

    # Commits this session
    if commits:
        parts.append(f"[commits: {len(commits)}]")

    return " ".join(parts) if parts else ""


# =============================================================================
# Stats Persistence (for next session)
# =============================================================================


def save_stats_for_next_session(
    changes: GitChanges,
    metrics: SessionMetrics,
    commits: list[dict[str, str]],
) -> None:
    """Save session stats for injection into next session."""
    from datetime import datetime

    stats = {
        "timestamp": datetime.now().isoformat(),
        "git": {
            "has_changes": changes.has_changes,
            "lines_added": changes.lines_added,
            "lines_deleted": changes.lines_deleted,
            "code_files": len(changes.code_files),
            "test_files": len(changes.test_files),
            "config_files": len(changes.config_files),
        },
        "session": {
            "tool_calls": metrics.tool_calls,
            "errors": metrics.errors,
            "error_rate": round(metrics.error_rate, 2),
        },
        "commits": len(commits),
        "formatted": format_session_stats(changes, metrics, commits),
    }

    try:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        LAST_SESSION_STATS_FILE.write_text(json.dumps(stats, indent=2))
        logger.info(f"Saved stats for next session: {stats['formatted']}")
    except OSError as e:
        logger.warning(f"Failed to save stats: {e}")


# =============================================================================
# Main Hook
# =============================================================================


def main() -> None:
    """Main hook entry point."""
    try:
        input_data: dict[str, Any] = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Analyze
    changes = get_uncommitted_changes()
    metrics = parse_session_metrics(input_data)
    commits = get_session_commits()

    # Always save stats for next session (even if minimal)
    save_stats_for_next_session(changes, metrics, commits)

    # Skip output if nothing interesting (but stats are saved)
    if not changes.has_changes and metrics.tool_calls < 5:
        logger.info("No significant activity, skipping output")
        print(json.dumps({}))
        sys.exit(0)

    # Format stats (shown at stop, but also saved for next session start)
    formatted = format_session_stats(changes, metrics, commits)

    if formatted:
        output = {"systemMessage": formatted}
        logger.info(f"Output: {formatted}")
    else:
        output = {}

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
