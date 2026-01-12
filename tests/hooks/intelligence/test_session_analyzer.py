"""Unit tests for session-analyzer hook."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add hooks to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "hooks" / "intelligence"))

from session_analyzer import (  # type: ignore
    GitChanges,
    SessionMetrics,
    categorize_file,
    format_session_stats,
    parse_session_metrics,
)

# =============================================================================
# GitChanges Tests
# =============================================================================


class TestGitChanges:
    """Tests for GitChanges dataclass."""

    def test_default_values(self) -> None:
        """Test default initialization."""
        changes = GitChanges()
        assert changes.has_changes is False
        assert changes.lines_added == 0
        assert changes.lines_deleted == 0
        assert changes.code_files == []
        assert changes.test_files == []
        assert changes.config_files == []
        assert changes.other_files == []

    def test_with_values(self) -> None:
        """Test initialization with values."""
        changes = GitChanges(
            has_changes=True,
            lines_added=50,
            lines_deleted=10,
            code_files=["src/main.py"],
        )
        assert changes.has_changes is True
        assert changes.lines_added == 50
        assert changes.lines_deleted == 10
        assert changes.code_files == ["src/main.py"]


# =============================================================================
# SessionMetrics Tests
# =============================================================================


class TestSessionMetrics:
    """Tests for SessionMetrics dataclass."""

    def test_error_rate_zero_calls(self) -> None:
        """Test error rate with zero tool calls."""
        metrics = SessionMetrics(tool_calls=0, errors=0)
        assert metrics.error_rate == 0.0

    def test_error_rate_calculation(self) -> None:
        """Test error rate calculation."""
        metrics = SessionMetrics(tool_calls=100, errors=25)
        assert metrics.error_rate == 0.25

    def test_error_rate_no_errors(self) -> None:
        """Test error rate with no errors."""
        metrics = SessionMetrics(tool_calls=50, errors=0)
        assert metrics.error_rate == 0.0


# =============================================================================
# categorize_file Tests
# =============================================================================


class TestCategorizeFile:
    """Tests for file categorization."""

    @pytest.mark.parametrize(
        "filepath,expected",
        [
            ("src/main.py", "code"),
            ("lib/utils.rs", "code"),
            ("app/index.ts", "code"),
            ("server.go", "code"),
        ],
    )
    def test_code_files(self, filepath: str, expected: str) -> None:
        """Test code file detection."""
        assert categorize_file(filepath) == expected

    @pytest.mark.parametrize(
        "filepath,expected",
        [
            ("tests/test_main.py", "test"),
            ("src/main_test.go", "test"),
            ("spec/utils.spec.ts", "test"),
            ("tests/integration/test_api.py", "test"),
        ],
    )
    def test_test_files(self, filepath: str, expected: str) -> None:
        """Test test file detection."""
        assert categorize_file(filepath) == expected

    @pytest.mark.parametrize(
        "filepath,expected",
        [
            ("config.json", "config"),
            ("settings.yaml", "config"),
            ("pyproject.toml", "config"),
            (".env", "config"),
        ],
    )
    def test_config_files(self, filepath: str, expected: str) -> None:
        """Test config file detection."""
        assert categorize_file(filepath) == expected

    @pytest.mark.parametrize(
        "filepath,expected",
        [
            ("README.md", "other"),
            ("LICENSE", "other"),
            ("Makefile", "other"),
        ],
    )
    def test_other_files(self, filepath: str, expected: str) -> None:
        """Test other file detection."""
        assert categorize_file(filepath) == expected


# =============================================================================
# parse_session_metrics Tests
# =============================================================================


class TestParseSessionMetrics:
    """Tests for session metrics parsing."""

    def test_empty_input(self) -> None:
        """Test with empty input."""
        metrics = parse_session_metrics({})
        assert metrics.tool_calls == 0
        assert metrics.errors == 0

    def test_with_session_data(self) -> None:
        """Test with session data."""
        input_data = {
            "session": {
                "tool_calls": 100,
                "errors": 15,
            }
        }
        metrics = parse_session_metrics(input_data)
        assert metrics.tool_calls == 100
        assert metrics.errors == 15

    def test_missing_fields(self) -> None:
        """Test with missing fields."""
        input_data = {"session": {"tool_calls": 50}}
        metrics = parse_session_metrics(input_data)
        assert metrics.tool_calls == 50
        assert metrics.errors == 0


# =============================================================================
# format_session_stats Tests
# =============================================================================


class TestFormatSessionStats:
    """Tests for session stats formatting."""

    def test_no_changes_no_metrics(self) -> None:
        """Test with no changes and no metrics."""
        changes = GitChanges()
        metrics = SessionMetrics()
        result = format_session_stats(changes, metrics, [])
        assert result == ""

    def test_with_uncommitted_changes(self) -> None:
        """Test with uncommitted changes."""
        changes = GitChanges(
            has_changes=True,
            lines_added=50,
            lines_deleted=10,
            code_files=["src/main.py", "src/utils.py"],
        )
        metrics = SessionMetrics()
        result = format_session_stats(changes, metrics, [])
        assert "[uncommitted:" in result
        assert "+50/-10" in result
        assert "2 code" in result

    def test_with_session_metrics(self) -> None:
        """Test with session metrics."""
        changes = GitChanges()
        metrics = SessionMetrics(tool_calls=100, errors=5)
        result = format_session_stats(changes, metrics, [])
        assert "[session:" in result
        assert "100 calls" in result
        assert "5 errors" in result

    def test_with_commits(self) -> None:
        """Test with commits."""
        changes = GitChanges()
        metrics = SessionMetrics(tool_calls=50, errors=0)
        commits = [
            {"hash": "abc123", "message": "feat: add feature"},
            {"hash": "def456", "message": "fix: bug fix"},
        ]
        result = format_session_stats(changes, metrics, commits)
        assert "[commits: 2]" in result

    def test_complete_output(self) -> None:
        """Test complete output with all components."""
        changes = GitChanges(
            has_changes=True,
            lines_added=100,
            lines_deleted=20,
            code_files=["a.py", "b.py"],
            test_files=["test_a.py"],
            config_files=["config.json"],
        )
        metrics = SessionMetrics(tool_calls=80, errors=10)
        commits = [{"hash": "abc", "message": "test"}]

        result = format_session_stats(changes, metrics, commits)

        assert "[uncommitted:" in result
        assert "+100/-20" in result
        assert "2 code" in result
        assert "1 test" in result
        assert "1 config" in result
        assert "[session:" in result
        assert "80 calls" in result
        assert "10 errors" in result
        assert "[commits: 1]" in result
