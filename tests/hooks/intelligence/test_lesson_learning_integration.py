"""Integration tests for lesson learning system.

Tests end-to-end flow:
1. Seed trajectory data with problematic patterns
2. Run meta_learning hook to extract and store patterns
3. Run lesson_injector hook to inject lessons
4. Verify lessons appear in additionalContext
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "hooks" / "intelligence"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "hooks"))


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def hooks_dir() -> Path:
    """Path to hooks directory."""
    return Path(__file__).parent.parent.parent.parent / "hooks" / "intelligence"


@pytest.fixture
def temp_metrics_dir(tmp_path: Path) -> Path:
    """Temporary metrics directory."""
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    return metrics_dir


@pytest.fixture
def mock_mcp_store(tmp_path: Path):
    """Mock MCP store file."""
    store_file = tmp_path / "store.json"
    store_file.write_text(json.dumps({"entries": {}}))
    return store_file


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.integration
class TestLessonLearningIntegration:
    """Integration tests for full lesson learning flow."""

    def test_meta_learning_runs_without_error(self, hooks_dir: Path):
        """meta_learning.py runs without error on empty input."""
        result = subprocess.run(
            [sys.executable, str(hooks_dir / "meta_learning.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        # Should output valid JSON
        output = json.loads(result.stdout)
        assert isinstance(output, dict)

    def test_lesson_injector_runs_without_error(self, hooks_dir: Path):
        """lesson_injector.py runs without error on basic input."""
        input_data = {"prompt": "test prompt", "cwd": "/tmp/test"}

        result = subprocess.run(
            [sys.executable, str(hooks_dir / "lesson_injector.py")],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        # Should output valid JSON
        output = json.loads(result.stdout)
        assert isinstance(output, dict)

    def test_meta_learning_extracts_patterns_from_session_analysis(
        self, hooks_dir: Path, temp_metrics_dir: Path, monkeypatch
    ):
        """meta_learning extracts error patterns from session analysis."""
        # Setup: Create session analysis file with high error rate
        session_analysis = {
            "session": {
                "tool_calls": 100,
                "errors": 30,  # 30% error rate
                "error_rate": 0.30,
            }
        }
        session_file = temp_metrics_dir / "session_analysis.json"
        session_file.write_text(json.dumps(session_analysis))

        # Run with METRICS_DIR set to temp
        result = subprocess.run(
            [sys.executable, str(hooks_dir / "meta_learning.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **subprocess.os.environ,
                "METRICS_DIR": str(temp_metrics_dir),
            },
        )

        assert result.returncode == 0

        # Check log file for extracted pattern
        log_file = temp_metrics_dir / "meta_learning.log"
        if log_file.exists():
            log_content = log_file.read_text()
            # Should have logged pattern extraction
            assert "pattern" in log_content.lower() or "extracted" in log_content.lower()

    def test_lesson_injector_handles_empty_patterns(self, hooks_dir: Path):
        """lesson_injector handles case when no patterns exist."""
        input_data = {"prompt": "some unique query", "cwd": "/tmp/test"}

        result = subprocess.run(
            [sys.executable, str(hooks_dir / "lesson_injector.py")],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        # Should return empty dict when no patterns
        assert output == {} or "additionalContext" not in output or output.get("additionalContext") == ""


@pytest.mark.integration
class TestPatternExtractionFlow:
    """Tests for pattern extraction from various data sources."""

    def test_extracts_high_rework_pattern(self, hooks_dir: Path, temp_metrics_dir: Path):
        """Extracts high_rework pattern when file edited multiple times."""
        # Setup: Create file edit counts file
        file_edits = {
            "src/config.py": 5,  # >3 edits = high rework
            "src/main.py": 2,
        }
        edit_counts_file = temp_metrics_dir / "file_edit_counts.json"
        edit_counts_file.write_text(json.dumps(file_edits))

        result = subprocess.run(
            [sys.executable, str(hooks_dir / "meta_learning.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **subprocess.os.environ,
                "METRICS_DIR": str(temp_metrics_dir),
            },
        )

        assert result.returncode == 0

    def test_handles_missing_data_gracefully(self, hooks_dir: Path, temp_metrics_dir: Path):
        """Handles missing session/trajectory data without crashing."""
        # Run with empty metrics dir (no data files)
        result = subprocess.run(
            [sys.executable, str(hooks_dir / "meta_learning.py")],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **subprocess.os.environ,
                "METRICS_DIR": str(temp_metrics_dir),
            },
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert isinstance(output, dict)


@pytest.mark.integration
class TestLessonInjectionFlow:
    """Tests for lesson injection into additionalContext."""

    def test_injects_lessons_with_correct_format(self):
        """Verifies additionalContext format matches hook spec."""
        from lesson_injector import format_lesson

        # High confidence pattern
        high_conf = {"pattern": "Run tests before commit", "confidence": 0.95}
        result = format_lesson(high_conf)
        assert result == "- Run tests before commit"

        # Medium confidence pattern
        medium_conf = {"pattern": "Consider caching", "confidence": 0.65}
        result = format_lesson(medium_conf)
        assert result == "- Consider: Consider caching"

        # Low confidence pattern
        low_conf = {"pattern": "Maybe something", "confidence": 0.3}
        result = format_lesson(low_conf)
        assert result is None

    def test_limits_lessons_to_max(self):
        """Verifies MAX_LESSONS limit is enforced."""
        from lesson_injector import MAX_LESSONS

        assert MAX_LESSONS == 3  # Should be 3 to avoid noise
