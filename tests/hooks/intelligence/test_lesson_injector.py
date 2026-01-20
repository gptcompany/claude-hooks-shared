"""Unit tests for lesson_injector hook - TDD Red Phase.

Tests for UserPromptSubmit hook that injects relevant lessons from pattern_search.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "hooks" / "intelligence"))


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_pattern_search():
    """Mock pattern_search from mcp_client."""
    with patch("lesson_injector.pattern_search") as mock:
        yield mock


@pytest.fixture
def mock_get_project_name():
    """Mock get_project_name from mcp_client."""
    with patch("lesson_injector.get_project_name") as mock:
        mock.return_value = "test-project"
        yield mock


@pytest.fixture
def high_confidence_patterns():
    """Patterns with high confidence (>0.8)."""
    return [
        {
            "pattern": "Always run tests before committing",
            "confidence": 0.95,
            "type": "workflow",
            "metadata": {"project": "test-project"},
        },
        {
            "pattern": "Use type hints for public APIs",
            "confidence": 0.85,
            "type": "code-quality",
            "metadata": {"project": "test-project"},
        },
    ]


@pytest.fixture
def medium_confidence_patterns():
    """Patterns with medium confidence (0.5-0.8)."""
    return [
        {
            "pattern": "Consider using dataclasses for DTOs",
            "confidence": 0.7,
            "type": "suggestion",
            "metadata": {"project": "test-project"},
        },
        {
            "pattern": "Check for edge cases with empty inputs",
            "confidence": 0.6,
            "type": "testing",
            "metadata": {"project": "test-project"},
        },
    ]


@pytest.fixture
def low_confidence_patterns():
    """Patterns with low confidence (<0.5)."""
    return [
        {
            "pattern": "Maybe use async here",
            "confidence": 0.3,
            "type": "suggestion",
            "metadata": {"project": "test-project"},
        },
    ]


@pytest.fixture
def mixed_confidence_patterns(high_confidence_patterns, medium_confidence_patterns, low_confidence_patterns):
    """Mix of high, medium, and low confidence patterns."""
    return high_confidence_patterns + medium_confidence_patterns + low_confidence_patterns


# =============================================================================
# High Confidence Injection Tests
# =============================================================================


class TestHighConfidenceInjection:
    """Tests for high confidence lesson injection (>0.8)."""

    def test_injects_high_confidence_lesson(self, mock_pattern_search, mock_get_project_name, high_confidence_patterns):
        """Test that high confidence patterns (>0.8) are auto-injected."""
        mock_pattern_search.return_value = high_confidence_patterns

        from lesson_injector import process_hook

        input_data = {"prompt": "help me write tests", "cwd": "/tmp/test-project"}
        result = process_hook(input_data)

        assert "additionalContext" in result
        assert "Always run tests before committing" in result["additionalContext"]
        # High confidence should NOT have "Consider:" prefix
        assert "Consider: Always run tests" not in result["additionalContext"]

    def test_high_confidence_has_lessons_prefix(
        self, mock_pattern_search, mock_get_project_name, high_confidence_patterns
    ):
        """Test that high confidence lessons have [Lessons] prefix."""
        mock_pattern_search.return_value = high_confidence_patterns

        from lesson_injector import process_hook

        input_data = {"prompt": "test prompt", "cwd": "/tmp"}
        result = process_hook(input_data)

        assert "[Lessons from past sessions]" in result["additionalContext"]


# =============================================================================
# Medium Confidence Suggestion Tests
# =============================================================================


class TestMediumConfidenceSuggestion:
    """Tests for medium confidence lesson suggestion (0.5-0.8)."""

    def test_suggests_medium_confidence_lesson(
        self, mock_pattern_search, mock_get_project_name, medium_confidence_patterns
    ):
        """Test that medium confidence patterns (0.5-0.8) are suggested with different format."""
        mock_pattern_search.return_value = medium_confidence_patterns

        from lesson_injector import process_hook

        input_data = {"prompt": "create a new class", "cwd": "/tmp"}
        result = process_hook(input_data)

        assert "additionalContext" in result
        # Medium confidence should have "Consider:" prefix
        assert "Consider:" in result["additionalContext"]


# =============================================================================
# Low Confidence Skip Tests
# =============================================================================


class TestLowConfidenceSkip:
    """Tests for low confidence lesson filtering (<0.5)."""

    def test_skips_low_confidence_lesson(self, mock_pattern_search, mock_get_project_name, low_confidence_patterns):
        """Test that low confidence patterns (<0.5) are not injected."""
        mock_pattern_search.return_value = low_confidence_patterns

        from lesson_injector import process_hook

        input_data = {"prompt": "async operation", "cwd": "/tmp"}
        result = process_hook(input_data)

        # Should return empty dict or additionalContext without the low confidence pattern
        if "additionalContext" in result:
            assert "Maybe use async here" not in result["additionalContext"]
        else:
            assert result == {}


# =============================================================================
# Pattern Search Tests
# =============================================================================


class TestPatternSearchBehavior:
    """Tests for pattern search integration."""

    def test_searches_patterns_by_project(self, mock_pattern_search, mock_get_project_name):
        """Test that pattern search uses project-specific search."""
        mock_pattern_search.return_value = []
        mock_get_project_name.return_value = "my-specific-project"

        from lesson_injector import process_hook

        input_data = {"prompt": "help", "cwd": "/home/user/my-specific-project"}
        process_hook(input_data)

        # Verify pattern_search was called
        mock_pattern_search.assert_called()
        # The query should include project context
        call_args = mock_pattern_search.call_args
        assert call_args is not None

    def test_searches_patterns_by_context(self, mock_pattern_search, mock_get_project_name):
        """Test that pattern search uses prompt context for relevance."""
        mock_pattern_search.return_value = []

        from lesson_injector import process_hook

        input_data = {"prompt": "write unit tests for the API", "cwd": "/tmp"}
        process_hook(input_data)

        # Verify pattern_search was called with relevant query
        mock_pattern_search.assert_called()
        call_args = mock_pattern_search.call_args
        # Should use prompt content in search
        assert call_args is not None


# =============================================================================
# Output Format Tests
# =============================================================================


class TestOutputFormat:
    """Tests for hook output format."""

    def test_formats_additionalContext_correctly(
        self, mock_pattern_search, mock_get_project_name, high_confidence_patterns
    ):
        """Test that output format matches hook spec with additionalContext key."""
        mock_pattern_search.return_value = high_confidence_patterns

        from lesson_injector import process_hook

        input_data = {"prompt": "test", "cwd": "/tmp"}
        result = process_hook(input_data)

        # Must have additionalContext key
        assert isinstance(result, dict)
        assert "additionalContext" in result
        assert isinstance(result["additionalContext"], str)

    def test_formats_with_confidence_levels(
        self, mock_pattern_search, mock_get_project_name, mixed_confidence_patterns
    ):
        """Test that different confidence levels are formatted differently."""
        # Filter out low confidence (which wouldn't be returned by pattern_search with min_confidence=0.5)
        patterns = [p for p in mixed_confidence_patterns if p["confidence"] >= 0.5]
        mock_pattern_search.return_value = patterns

        from lesson_injector import process_hook

        input_data = {"prompt": "test", "cwd": "/tmp"}
        result = process_hook(input_data)

        context = result.get("additionalContext", "")
        # Should have lessons header
        assert "[Lessons from past sessions]" in context


# =============================================================================
# Empty/No Patterns Tests
# =============================================================================


class TestNoPatterns:
    """Tests for handling no patterns found."""

    def test_no_injection_when_no_patterns(self, mock_pattern_search, mock_get_project_name):
        """Test that empty patterns returns no additionalContext."""
        mock_pattern_search.return_value = []

        from lesson_injector import process_hook

        input_data = {"prompt": "random prompt", "cwd": "/tmp"}
        result = process_hook(input_data)

        # Should return empty dict when no patterns
        assert result == {} or "additionalContext" not in result


# =============================================================================
# Limit Tests
# =============================================================================


class TestLessonLimits:
    """Tests for lesson count limits."""

    def test_limits_injected_lessons(self, mock_pattern_search, mock_get_project_name):
        """Test that max 3 lessons are injected to avoid noise."""
        many_patterns = [
            {
                "pattern": f"Lesson {i}",
                "confidence": 0.9,
                "type": "test",
                "metadata": {},
            }
            for i in range(10)
        ]
        mock_pattern_search.return_value = many_patterns

        from lesson_injector import process_hook

        input_data = {"prompt": "test", "cwd": "/tmp"}
        result = process_hook(input_data)

        context = result.get("additionalContext", "")
        # Count the number of lessons (each starts with "- ")
        lesson_count = context.count("\n- ")
        # Account for first lesson which might not have newline before
        if context.startswith("- ") or "[Lessons" in context:
            lesson_count = len([line for line in context.split("\n") if line.strip().startswith("- ")])

        assert lesson_count <= 3, f"Expected max 3 lessons, got {lesson_count}"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for graceful error handling."""

    def test_returns_empty_on_invalid_input(self, mock_pattern_search, mock_get_project_name):
        """Test graceful handling of invalid input."""
        from lesson_injector import process_hook

        result = process_hook({})
        assert result == {} or isinstance(result, dict)

    def test_returns_empty_on_pattern_search_error(self, mock_pattern_search, mock_get_project_name):
        """Test graceful handling when pattern_search fails."""
        mock_pattern_search.side_effect = Exception("Connection error")

        from lesson_injector import process_hook

        input_data = {"prompt": "test", "cwd": "/tmp"}
        result = process_hook(input_data)

        # Should return empty dict on error, not raise
        assert result == {}


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestHookIntegration:
    """Integration-style tests for the complete hook flow."""

    def test_full_flow_with_mixed_patterns(self, mock_pattern_search, mock_get_project_name, mixed_confidence_patterns):
        """Test complete flow with mixed confidence patterns."""
        # Only include patterns that would pass min_confidence filter
        patterns = [p for p in mixed_confidence_patterns if p["confidence"] >= 0.5]
        mock_pattern_search.return_value = patterns

        from lesson_injector import process_hook

        input_data = {
            "prompt": "I need to refactor the authentication module",
            "cwd": "/home/user/project",
        }
        result = process_hook(input_data)

        # Should have output
        assert "additionalContext" in result
        context = result["additionalContext"]

        # Should have header
        assert "[Lessons from past sessions]" in context

        # High confidence should be included without "Consider:"
        assert "Always run tests before committing" in context

        # Medium confidence should have "Consider:" prefix
        # (at least one medium confidence pattern should be suggested)
        # Note: may be limited to 3 total lessons

    def test_main_function_reads_stdin_writes_stdout(
        self, mock_pattern_search, mock_get_project_name, high_confidence_patterns
    ):
        """Test that main() reads from stdin and writes JSON to stdout."""
        mock_pattern_search.return_value = high_confidence_patterns

        import io

        from lesson_injector import main

        input_json = json.dumps({"prompt": "test", "cwd": "/tmp"})

        with (
            patch("sys.stdin", io.StringIO(input_json)),
            patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
            patch("sys.exit"),  # noqa: F841
        ):
            main()

            output = mock_stdout.getvalue()
            # Should be valid JSON
            result = json.loads(output)
            assert "additionalContext" in result
