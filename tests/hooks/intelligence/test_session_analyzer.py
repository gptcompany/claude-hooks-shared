"""Unit tests for session-analyzer hook."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add hooks to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "hooks" / "intelligence"))

from session_analyzer import (  # type: ignore  # noqa: E402
    THRESHOLD_CONFIG_FILES,
    THRESHOLD_ERROR_RATE,
    THRESHOLD_LINES_CHANGED,
    THRESHOLD_LONG_SESSION,
    THRESHOLD_MIN_ERRORS,
    THRESHOLD_MIN_TOOL_CALLS,
    GitChanges,
    SessionMetrics,
    Suggestion,
    categorize_file,
    format_session_stats,
    format_suggestions,
    get_suggestions,
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

    def test_with_suggestions(self) -> None:
        """Test output includes suggestions when provided."""
        changes = GitChanges(has_changes=True, lines_added=100)
        metrics = SessionMetrics(tool_calls=50, errors=0)
        suggestions = [Suggestion(command="/review", trigger="uncommitted", priority=3)]

        result = format_session_stats(changes, metrics, [], suggestions)

        assert "[suggest:" in result
        assert "/review" in result


# =============================================================================
# Suggestion Tests
# =============================================================================


class TestSuggestion:
    """Tests for Suggestion dataclass."""

    def test_suggestion_creation(self) -> None:
        """Test creating a suggestion."""
        suggestion = Suggestion(command="/review", trigger="uncommitted", priority=3)
        assert suggestion.command == "/review"
        assert suggestion.trigger == "uncommitted"
        assert suggestion.priority == 3


# =============================================================================
# format_suggestions Tests
# =============================================================================


class TestFormatSuggestions:
    """Tests for suggestion formatting."""

    def test_empty_suggestions(self) -> None:
        """Test with no suggestions."""
        result = format_suggestions([])
        assert result == ""

    def test_single_suggestion(self) -> None:
        """Test with single suggestion."""
        suggestions = [Suggestion(command="/review", trigger="uncommitted", priority=3)]
        result = format_suggestions(suggestions)
        assert result == "[suggest: /review]"

    def test_multiple_suggestions(self) -> None:
        """Test with multiple suggestions."""
        suggestions = [
            Suggestion(command="/undo:checkpoint", trigger="errors", priority=1),
            Suggestion(command="/review", trigger="uncommitted", priority=3),
        ]
        result = format_suggestions(suggestions)
        assert result == "[suggest: /undo:checkpoint, /review]"


# =============================================================================
# get_suggestions Tests
# =============================================================================


class TestGetSuggestions:
    """Tests for contextual suggestion generation."""

    def test_short_session_no_suggestions(self) -> None:
        """Test that short sessions get no suggestions."""
        changes = GitChanges(has_changes=True, lines_added=100)
        metrics = SessionMetrics(tool_calls=3, errors=2)  # Below threshold

        suggestions = get_suggestions(changes, metrics)

        assert suggestions == []

    def test_clean_session_no_suggestions(self) -> None:
        """Test clean session with no issues."""
        changes = GitChanges(has_changes=True, lines_added=20)  # Below threshold
        metrics = SessionMetrics(tool_calls=10, errors=0)

        suggestions = get_suggestions(changes, metrics)

        assert suggestions == []

    def test_high_error_rate_suggests_checkpoint(self) -> None:
        """Test high error rate triggers checkpoint suggestion."""
        changes = GitChanges()
        # 30% error rate with enough errors
        metrics = SessionMetrics(tool_calls=20, errors=6)

        suggestions = get_suggestions(changes, metrics)

        assert len(suggestions) >= 1
        assert any(s.command == "/undo:checkpoint" for s in suggestions)
        assert any(s.trigger == "errors" for s in suggestions)

    def test_high_error_rate_low_count_no_suggestion(self) -> None:
        """Test high error rate but few errors doesn't trigger."""
        changes = GitChanges()
        # 50% error rate but only 2 errors (below min threshold)
        metrics = SessionMetrics(tool_calls=4, errors=2)

        # This session is too short anyway
        suggestions = get_suggestions(changes, metrics)
        assert suggestions == []

        # Try with enough calls but still few errors
        metrics2 = SessionMetrics(tool_calls=10, errors=3)  # 30% but only 3 errors
        suggestions2 = get_suggestions(changes, metrics2)
        # Should not trigger because errors < THRESHOLD_MIN_ERRORS
        checkpoint_suggestions = [s for s in suggestions2 if s.command == "/undo:checkpoint"]
        assert len(checkpoint_suggestions) == 0

    def test_many_config_files_suggests_health(self) -> None:
        """Test multiple config file changes triggers health check."""
        changes = GitChanges(
            has_changes=True,
            config_files=["a.json", "b.yaml", "c.toml"],
        )
        metrics = SessionMetrics(tool_calls=10, errors=0)

        suggestions = get_suggestions(changes, metrics)

        assert len(suggestions) >= 1
        assert any(s.command == "/health" for s in suggestions)
        assert any(s.trigger == "config" for s in suggestions)

    def test_significant_changes_suggests_review(self) -> None:
        """Test significant uncommitted changes triggers review."""
        changes = GitChanges(
            has_changes=True,
            lines_added=100,  # Above threshold
            code_files=["main.py"],
        )
        metrics = SessionMetrics(tool_calls=10, errors=0)

        suggestions = get_suggestions(changes, metrics)

        assert len(suggestions) >= 1
        assert any(s.command == "/review" for s in suggestions)
        assert any(s.trigger == "uncommitted" for s in suggestions)

    def test_long_session_suggests_context(self) -> None:
        """Test long session triggers context check."""
        changes = GitChanges()
        metrics = SessionMetrics(tool_calls=70, errors=0)  # Above threshold

        suggestions = get_suggestions(changes, metrics)

        assert len(suggestions) >= 1
        assert any(s.command == "/context" for s in suggestions)
        assert any(s.trigger == "long" for s in suggestions)

    def test_multiple_triggers_limited_to_two(self) -> None:
        """Test that max 2 suggestions are returned."""
        changes = GitChanges(
            has_changes=True,
            lines_added=100,
            config_files=["a.json", "b.yaml"],
        )
        # Trigger all conditions
        metrics = SessionMetrics(tool_calls=70, errors=20)  # High errors + long

        suggestions = get_suggestions(changes, metrics)

        assert len(suggestions) <= 2

    def test_suggestions_sorted_by_priority(self) -> None:
        """Test suggestions are sorted by priority (lowest first)."""
        changes = GitChanges(
            has_changes=True,
            lines_added=100,
            config_files=["a.json", "b.yaml"],
        )
        metrics = SessionMetrics(tool_calls=70, errors=20)

        suggestions = get_suggestions(changes, metrics)

        # Should be sorted by priority
        if len(suggestions) >= 2:
            assert suggestions[0].priority <= suggestions[1].priority

    def test_priority_1_errors_comes_first(self) -> None:
        """Test error suggestion (priority 1) comes before others."""
        changes = GitChanges(
            has_changes=True,
            lines_added=100,
            config_files=["a.json", "b.yaml"],
        )
        metrics = SessionMetrics(tool_calls=30, errors=10)  # 33% error rate

        suggestions = get_suggestions(changes, metrics)

        assert len(suggestions) >= 1
        assert suggestions[0].command == "/undo:checkpoint"
        assert suggestions[0].priority == 1


# =============================================================================
# Threshold Constants Tests
# =============================================================================


class TestThresholdConstants:
    """Tests to verify threshold constants are reasonable."""

    def test_error_rate_threshold_reasonable(self) -> None:
        """Verify error rate threshold is between 0 and 1."""
        assert 0 < THRESHOLD_ERROR_RATE < 1
        assert THRESHOLD_ERROR_RATE == 0.25  # 25%

    def test_min_errors_threshold_reasonable(self) -> None:
        """Verify minimum errors threshold prevents false positives."""
        assert THRESHOLD_MIN_ERRORS >= 3
        assert THRESHOLD_MIN_ERRORS == 5

    def test_lines_changed_threshold_reasonable(self) -> None:
        """Verify lines changed threshold is meaningful."""
        assert THRESHOLD_LINES_CHANGED >= 30
        assert THRESHOLD_LINES_CHANGED == 50

    def test_config_files_threshold_reasonable(self) -> None:
        """Verify config files threshold catches multiple changes."""
        assert THRESHOLD_CONFIG_FILES >= 2
        assert THRESHOLD_CONFIG_FILES == 2

    def test_long_session_threshold_reasonable(self) -> None:
        """Verify long session threshold is meaningful."""
        assert THRESHOLD_LONG_SESSION >= 40
        assert THRESHOLD_LONG_SESSION == 60

    def test_min_tool_calls_threshold_reasonable(self) -> None:
        """Verify minimum tool calls prevents false positives."""
        assert THRESHOLD_MIN_TOOL_CALLS >= 3
        assert THRESHOLD_MIN_TOOL_CALLS == 5
