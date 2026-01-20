"""Unit tests for meta_learning Stop hook.

TDD Red Phase: Tests written first before implementation.
Tests for pattern extraction from session data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add hooks to path for import
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent.parent / "hooks" / "intelligence")
)

# Will fail until meta_learning.py is created
from meta_learning import (  # type: ignore  # noqa: E402
    THRESHOLD_REWORK_EDITS,
    THRESHOLD_ERROR_RATE,
    THRESHOLD_QUALITY_DROP,
    extract_rework_pattern,
    extract_error_pattern,
    extract_quality_drop_pattern,
    extract_patterns,
    calculate_confidence,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_trajectory_index() -> list[dict[str, Any]]:
    """Sample trajectory index data."""
    return [
        {
            "id": "traj-001",
            "task": "Fix bug in auth module",
            "success": True,
            "steps": 5,
            "timestamp": "2024-01-20T10:00:00Z",
        },
        {
            "id": "traj-002",
            "task": "Refactor database layer",
            "success": False,
            "steps": 8,
            "timestamp": "2024-01-20T10:30:00Z",
        },
        {
            "id": "traj-003",
            "task": "Add new feature",
            "success": True,
            "steps": 3,
            "timestamp": "2024-01-20T11:00:00Z",
        },
    ]


@pytest.fixture
def mock_session_analysis() -> dict[str, Any]:
    """Sample session analyzer output."""
    return {
        "timestamp": "2024-01-20T12:00:00Z",
        "git": {
            "has_changes": True,
            "lines_added": 150,
            "lines_deleted": 30,
            "code_files": 5,
            "test_files": 2,
            "config_files": 1,
        },
        "session": {
            "tool_calls": 100,
            "errors": 20,
            "error_rate": 0.20,
        },
        "commits": 3,
        "suggestions": [],
    }


@pytest.fixture
def mock_session_analysis_high_error() -> dict[str, Any]:
    """Session analysis with high error rate (>25%)."""
    return {
        "timestamp": "2024-01-20T12:00:00Z",
        "git": {"has_changes": True, "lines_added": 50, "lines_deleted": 10},
        "session": {
            "tool_calls": 100,
            "errors": 30,
            "error_rate": 0.30,
        },
        "commits": 1,
        "suggestions": [
            {"command": "/undo:checkpoint", "trigger": "errors", "priority": 1}
        ],
    }


@pytest.fixture
def mock_file_edit_counts_high_rework() -> dict[str, int]:
    """File edit counts showing high rework (>3 edits on same file)."""
    return {
        "src/main.py": 5,  # High rework
        "src/utils.py": 4,  # High rework
        "tests/test_main.py": 2,
        "config.json": 1,
    }


@pytest.fixture
def mock_file_edit_counts_normal() -> dict[str, int]:
    """File edit counts showing normal editing patterns."""
    return {
        "src/main.py": 2,
        "src/utils.py": 1,
        "tests/test_main.py": 1,
    }


@pytest.fixture
def mock_quality_scores_declining() -> list[float]:
    """Quality scores showing declining trend."""
    return [0.95, 0.88, 0.82, 0.75, 0.68]  # Clear decline


@pytest.fixture
def mock_quality_scores_stable() -> list[float]:
    """Quality scores showing stable/improving trend."""
    return [0.80, 0.82, 0.85, 0.88, 0.90]  # Improving


# =============================================================================
# Test extract_rework_pattern
# =============================================================================


class TestExtractReworkPattern:
    """Tests for high rework pattern detection."""

    def test_detects_high_rework(
        self, mock_file_edit_counts_high_rework: dict[str, int]
    ) -> None:
        """Test detection of files with >3 edits."""
        pattern = extract_rework_pattern(mock_file_edit_counts_high_rework)

        assert pattern is not None
        assert pattern["type"] == "high_rework"
        assert len(pattern["files"]) == 2  # src/main.py and src/utils.py
        assert "src/main.py" in pattern["files"]
        assert "src/utils.py" in pattern["files"]

    def test_no_pattern_on_normal_editing(
        self, mock_file_edit_counts_normal: dict[str, int]
    ) -> None:
        """Test no pattern when editing is normal."""
        pattern = extract_rework_pattern(mock_file_edit_counts_normal)

        assert pattern is None

    def test_threshold_boundary_exactly_3(self) -> None:
        """Test that exactly 3 edits does not trigger pattern."""
        file_counts = {"src/main.py": 3}  # Exactly at threshold
        pattern = extract_rework_pattern(file_counts)

        assert pattern is None  # Should not trigger (threshold is >3)

    def test_threshold_boundary_4_edits(self) -> None:
        """Test that 4 edits triggers pattern."""
        file_counts = {"src/main.py": 4}  # Above threshold
        pattern = extract_rework_pattern(file_counts)

        assert pattern is not None
        assert pattern["type"] == "high_rework"

    def test_empty_input(self) -> None:
        """Test with empty file counts."""
        pattern = extract_rework_pattern({})

        assert pattern is None


# =============================================================================
# Test extract_error_pattern
# =============================================================================


class TestExtractErrorPattern:
    """Tests for high error rate pattern detection."""

    def test_detects_high_error_rate(
        self, mock_session_analysis_high_error: dict[str, Any]
    ) -> None:
        """Test detection of >25% error rate."""
        pattern = extract_error_pattern(mock_session_analysis_high_error)

        assert pattern is not None
        assert pattern["type"] == "high_error"
        assert pattern["error_rate"] == 0.30
        assert pattern["total_errors"] == 30

    def test_no_pattern_on_low_error_rate(
        self, mock_session_analysis: dict[str, Any]
    ) -> None:
        """Test no pattern when error rate is below threshold."""
        pattern = extract_error_pattern(mock_session_analysis)

        assert pattern is None  # 20% is below 25% threshold

    def test_threshold_boundary_exactly_25(self) -> None:
        """Test that exactly 25% error rate does not trigger pattern."""
        session = {"session": {"tool_calls": 100, "errors": 25, "error_rate": 0.25}}
        pattern = extract_error_pattern(session)

        assert pattern is None  # Should not trigger (threshold is >25%)

    def test_threshold_boundary_26(self) -> None:
        """Test that 26% error rate triggers pattern."""
        session = {"session": {"tool_calls": 100, "errors": 26, "error_rate": 0.26}}
        pattern = extract_error_pattern(session)

        assert pattern is not None
        assert pattern["type"] == "high_error"

    def test_empty_session(self) -> None:
        """Test with empty session data."""
        pattern = extract_error_pattern({})

        assert pattern is None

    def test_missing_error_rate_field(self) -> None:
        """Test when error_rate field is missing but errors/calls are present."""
        session = {"session": {"tool_calls": 100, "errors": 30}}
        pattern = extract_error_pattern(session)

        # Should calculate error_rate from errors/tool_calls
        assert pattern is not None
        assert pattern["type"] == "high_error"


# =============================================================================
# Test extract_quality_drop_pattern
# =============================================================================


class TestExtractQualityDropPattern:
    """Tests for quality trend decline pattern detection."""

    def test_detects_quality_decline(
        self, mock_quality_scores_declining: list[float]
    ) -> None:
        """Test detection of declining quality trend."""
        pattern = extract_quality_drop_pattern(mock_quality_scores_declining)

        assert pattern is not None
        assert pattern["type"] == "quality_drop"
        assert pattern["trend"] == "declining"
        assert pattern["start_quality"] == pytest.approx(0.95, rel=0.01)
        assert pattern["end_quality"] == pytest.approx(0.68, rel=0.01)

    def test_no_pattern_on_stable_quality(
        self, mock_quality_scores_stable: list[float]
    ) -> None:
        """Test no pattern when quality is stable or improving."""
        pattern = extract_quality_drop_pattern(mock_quality_scores_stable)

        assert pattern is None

    def test_insufficient_data(self) -> None:
        """Test with insufficient data points."""
        pattern = extract_quality_drop_pattern([0.9, 0.8])  # Only 2 points

        assert pattern is None  # Need at least 3 points for trend

    def test_empty_scores(self) -> None:
        """Test with empty quality scores."""
        pattern = extract_quality_drop_pattern([])

        assert pattern is None

    def test_minor_fluctuation_not_detected(self) -> None:
        """Test that minor fluctuations don't trigger pattern."""
        scores = [0.85, 0.83, 0.84, 0.82, 0.83]  # Minor fluctuation
        pattern = extract_quality_drop_pattern(scores)

        assert pattern is None  # Not a significant drop


# =============================================================================
# Test pattern_stored_with_confidence
# =============================================================================


class TestPatternStoredWithConfidence:
    """Tests for pattern storage with confidence score."""

    @patch("meta_learning.pattern_store")
    def test_pattern_stored_via_mcp_client(self, mock_pattern_store: MagicMock) -> None:
        """Test that patterns are stored via mcp_client.pattern_store()."""
        mock_pattern_store.return_value = {"success": True}

        patterns = [
            {"type": "high_rework", "files": ["main.py"], "confidence": 0.85},
        ]

        # Import and call the function that stores patterns
        from meta_learning import store_patterns

        store_patterns(patterns)

        mock_pattern_store.assert_called_once()
        call_args = mock_pattern_store.call_args
        assert call_args[0][0] == "high_rework"  # pattern name
        assert call_args[0][1] == "high_rework"  # pattern type
        assert call_args[0][2] == 0.85  # confidence

    @patch("meta_learning.pattern_store")
    def test_multiple_patterns_all_stored(self, mock_pattern_store: MagicMock) -> None:
        """Test that all extracted patterns are stored."""
        mock_pattern_store.return_value = {"success": True}

        patterns = [
            {"type": "high_rework", "files": ["main.py"], "confidence": 0.85},
            {"type": "high_error", "error_rate": 0.30, "confidence": 0.90},
        ]

        from meta_learning import store_patterns

        store_patterns(patterns)

        assert mock_pattern_store.call_count == 2


# =============================================================================
# Test calculate_confidence
# =============================================================================


class TestCalculateConfidence:
    """Tests for confidence score calculation."""

    def test_high_confidence_for_strong_signal(self) -> None:
        """Test high confidence for strong signals."""
        # 6 edits on same file is a strong signal
        confidence = calculate_confidence(
            "high_rework", {"edit_count": 6, "threshold": 3}
        )

        assert confidence >= 0.8
        assert confidence <= 1.0

    def test_low_confidence_for_weak_signal(self) -> None:
        """Test lower confidence for borderline cases."""
        # 4 edits is just above threshold
        confidence = calculate_confidence(
            "high_rework", {"edit_count": 4, "threshold": 3}
        )

        assert confidence >= 0.5
        assert confidence < 0.8

    def test_confidence_bounded(self) -> None:
        """Test confidence is always between 0 and 1."""
        confidence1 = calculate_confidence("high_error", {"error_rate": 0.99})
        confidence2 = calculate_confidence("high_error", {"error_rate": 0.26})

        assert 0.0 <= confidence1 <= 1.0
        assert 0.0 <= confidence2 <= 1.0


# =============================================================================
# Test no_pattern_on_good_session
# =============================================================================


class TestNoPatternOnGoodSession:
    """Tests to ensure no patterns are extracted for healthy sessions."""

    def test_healthy_session_no_patterns(
        self,
        mock_trajectory_index: list[dict[str, Any]],
        mock_session_analysis: dict[str, Any],
        mock_file_edit_counts_normal: dict[str, int],
        mock_quality_scores_stable: list[float],
    ) -> None:
        """Test that healthy sessions produce no patterns."""
        patterns = extract_patterns(
            trajectory_index=mock_trajectory_index,
            session_analysis=mock_session_analysis,
            file_edit_counts=mock_file_edit_counts_normal,
            quality_scores=mock_quality_scores_stable,
        )

        assert patterns == []

    def test_empty_data_no_patterns(self) -> None:
        """Test that empty data produces no patterns."""
        patterns = extract_patterns(
            trajectory_index=[],
            session_analysis={},
            file_edit_counts={},
            quality_scores=[],
        )

        assert patterns == []


# =============================================================================
# Test reads_trajectory_data
# =============================================================================


class TestReadsTrajectoryData:
    """Tests for reading trajectory data from memory."""

    @patch("meta_learning.memory_retrieve")
    def test_reads_from_trajectory_index(self, mock_memory_retrieve: MagicMock) -> None:
        """Test that trajectory index is read from memory."""
        mock_memory_retrieve.return_value = [
            {"id": "traj-001", "success": True, "steps": 5},
        ]

        from meta_learning import load_trajectory_data

        project = "test-project"
        data = load_trajectory_data(project)

        mock_memory_retrieve.assert_called_with(f"trajectory:{project}:index")
        assert data is not None
        assert len(data) == 1

    @patch("meta_learning.memory_retrieve")
    def test_handles_missing_trajectory_data(
        self, mock_memory_retrieve: MagicMock
    ) -> None:
        """Test graceful handling when trajectory data is missing."""
        mock_memory_retrieve.return_value = None

        from meta_learning import load_trajectory_data

        data = load_trajectory_data("test-project")

        assert data == []


# =============================================================================
# Test reads_session_analyzer_data
# =============================================================================


class TestReadsSessionAnalyzerData:
    """Tests for reading session analyzer output."""

    def test_reads_from_session_analysis_file(self, tmp_path: Path) -> None:
        """Test reading from session_analysis.json file."""
        analysis_data = {
            "timestamp": "2024-01-20T12:00:00Z",
            "session": {"tool_calls": 50, "errors": 5, "error_rate": 0.10},
        }

        analysis_file = tmp_path / "session_analysis.json"
        analysis_file.write_text(json.dumps(analysis_data))

        from meta_learning import load_session_analysis

        with patch("meta_learning.SESSION_ANALYSIS_FILE", analysis_file):
            data = load_session_analysis()

        assert data is not None
        assert data["session"]["tool_calls"] == 50

    def test_handles_missing_session_file(self, tmp_path: Path) -> None:
        """Test graceful handling when session file is missing."""
        from meta_learning import load_session_analysis

        missing_file = tmp_path / "nonexistent.json"

        with patch("meta_learning.SESSION_ANALYSIS_FILE", missing_file):
            data = load_session_analysis()

        assert data == {}

    def test_handles_corrupt_session_file(self, tmp_path: Path) -> None:
        """Test graceful handling of corrupt JSON."""
        corrupt_file = tmp_path / "corrupt.json"
        corrupt_file.write_text("not valid json {{{")

        from meta_learning import load_session_analysis

        with patch("meta_learning.SESSION_ANALYSIS_FILE", corrupt_file):
            data = load_session_analysis()

        assert data == {}


# =============================================================================
# Integration Test - main()
# =============================================================================


class TestMainFunction:
    """Integration tests for main hook function."""

    @patch("meta_learning.pattern_store")
    @patch("meta_learning.memory_retrieve")
    def test_main_extracts_and_stores_patterns(
        self,
        mock_memory_retrieve: MagicMock,
        mock_pattern_store: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test main function extracts patterns and stores them."""
        # Setup mocks
        mock_memory_retrieve.return_value = [
            {"id": "traj-001", "success": False, "steps": 3},
            {"id": "traj-002", "success": False, "steps": 5},
        ]
        mock_pattern_store.return_value = {"success": True}

        # Create session analysis file with high error rate
        analysis_file = tmp_path / "session_analysis.json"
        analysis_file.write_text(
            json.dumps(
                {
                    "session": {"tool_calls": 100, "errors": 30, "error_rate": 0.30},
                }
            )
        )

        # Run main with empty stdin
        with (
            patch("meta_learning.SESSION_ANALYSIS_FILE", analysis_file),
            patch("sys.stdin.isatty", return_value=True),
        ):
            # Import and call main
            import meta_learning

            result = meta_learning.main()

        # Verify patterns were stored
        assert mock_pattern_store.called

    @patch("meta_learning.pattern_store")
    @patch("meta_learning.memory_retrieve")
    def test_main_returns_zero_on_success(
        self,
        mock_memory_retrieve: MagicMock,
        mock_pattern_store: MagicMock,
    ) -> None:
        """Test main returns 0 exit code on success."""
        mock_memory_retrieve.return_value = []
        mock_pattern_store.return_value = {"success": True}

        with patch("sys.stdin.isatty", return_value=True):
            import meta_learning

            result = meta_learning.main()

        assert result == 0

    @patch("meta_learning.memory_retrieve")
    def test_main_returns_zero_on_error(self, mock_memory_retrieve: MagicMock) -> None:
        """Test main returns 0 even on errors (graceful failure)."""
        mock_memory_retrieve.side_effect = Exception("Connection error")

        with patch("sys.stdin.isatty", return_value=True):
            import meta_learning

            result = meta_learning.main()

        assert result == 0  # Always return 0 for graceful failure


# =============================================================================
# Threshold Constants Tests
# =============================================================================


class TestThresholdConstants:
    """Tests to verify threshold constants are reasonable."""

    def test_rework_threshold_reasonable(self) -> None:
        """Verify rework threshold is meaningful."""
        assert THRESHOLD_REWORK_EDITS >= 3
        assert THRESHOLD_REWORK_EDITS == 3  # >3 means 4+ edits triggers

    def test_error_rate_threshold_reasonable(self) -> None:
        """Verify error rate threshold is between 0 and 1."""
        assert 0 < THRESHOLD_ERROR_RATE < 1
        assert THRESHOLD_ERROR_RATE == 0.25  # 25%

    def test_quality_drop_threshold_reasonable(self) -> None:
        """Verify quality drop threshold is meaningful."""
        assert 0 < THRESHOLD_QUALITY_DROP < 0.5
        assert THRESHOLD_QUALITY_DROP == 0.15  # 15% drop considered significant
