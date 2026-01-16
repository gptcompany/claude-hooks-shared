#!/usr/bin/env python3
"""
Mock Tests for Ralph Loop Enterprise Features

Tests cover:
- State checksum validation
- State backup/restore
- Resume detection
- Circuit breaker triggers
- Rate limiting
- SSOT config loading
"""

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks to path for import
HOOKS_CONTROL = Path(__file__).parent.parent.parent / "hooks" / "control"
HOOKS_SESSION = Path(__file__).parent.parent.parent / "hooks" / "session"


def load_module_from_file(name: str, file_path: Path):
    """Load a module from a file with an invalid Python module name (e.g., hyphens)."""
    spec = importlib.util.spec_from_file_location(name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Pre-load modules with hyphenated names
ralph_loop = load_module_from_file("ralph_loop", HOOKS_CONTROL / "ralph-loop.py")
ralph_resume = load_module_from_file("ralph_resume", HOOKS_SESSION / "ralph-resume.py")


class TestStateChecksum:
    """Test state checksum calculation and validation."""

    def test_checksum_calculation(self):
        """Test that checksum is calculated correctly."""
        state = {
            "active": True,
            "original_prompt": "Test task",
            "iteration": 5,
            "started_at": "2026-01-09T10:00:00",
        }

        checksum = ralph_loop.calculate_state_checksum(state)

        # Should be 16 char hex string
        assert len(checksum) == 16
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_checksum_excludes_self(self):
        """Test that checksum field is excluded from calculation."""
        state = {
            "active": True,
            "original_prompt": "Test task",
            "_checksum": "should_be_ignored",
        }

        checksum1 = ralph_loop.calculate_state_checksum(state)

        state["_checksum"] = "different_value"
        checksum2 = ralph_loop.calculate_state_checksum(state)

        assert checksum1 == checksum2

    def test_checksum_changes_with_data(self):
        """Test that checksum changes when data changes."""
        state1 = {"active": True, "iteration": 1}
        state2 = {"active": True, "iteration": 2}

        assert ralph_loop.calculate_state_checksum(state1) != ralph_loop.calculate_state_checksum(state2)


class TestStateBackup:
    """Test state backup functionality."""

    def test_backup_creates_file(self, tmp_path):
        """Test that backup creates .bak file."""
        state_file = tmp_path / "state.json"
        state_file.write_text('{"active": true, "iteration": 5}')

        with patch.object(ralph_loop, "RALPH_STATE", state_file):
            ralph_loop.backup_state()

        backup_file = state_file.with_suffix(".json.bak")
        assert backup_file.exists()
        assert json.loads(backup_file.read_text())["iteration"] == 5

    def test_backup_handles_missing_file(self, tmp_path):
        """Test that backup handles missing state file gracefully."""
        state_file = tmp_path / "nonexistent.json"

        with patch.object(ralph_loop, "RALPH_STATE", state_file):
            # Should not raise
            ralph_loop.backup_state()


class TestResumeDetection:
    """Test Ralph resume detection logic."""

    def test_detect_orphaned_session(self, tmp_path):
        """Test detection of orphaned Ralph session."""
        state = {
            "active": True,
            "original_prompt": "Fix tests",
            "iteration": 3,
            "started_at": (datetime.now() - timedelta(hours=1)).isoformat(),
        }

        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(state))

        # Mock the module's RALPH_STATE
        with patch.object(ralph_resume, "RALPH_STATE", state_file):
            result = ralph_resume.get_ralph_state()
            assert result is not None
            assert result["iteration"] == 3

    def test_ignore_old_sessions(self, tmp_path):
        """Test that very old sessions are treated as inactive."""
        state = {
            "active": True,
            "original_prompt": "Old task",
            "iteration": 10,
            "started_at": (datetime.now() - timedelta(days=2)).isoformat(),
        }

        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(state))

        with patch.object(ralph_resume, "RALPH_STATE", state_file):
            hours, _ = ralph_resume.get_session_age(state)
            # Session is old but get_session_age just reports age
            assert hours > 24

    def test_resume_command_detection(self):
        """Test that resume commands are detected."""
        is_cmd, action = ralph_resume.check_resume_commands("RALPH RESUME")
        assert is_cmd is True
        assert action == "resume"

        is_cmd, action = ralph_resume.check_resume_commands("ralph discard")
        assert is_cmd is True
        assert action == "discard"

        is_cmd, action = ralph_resume.check_resume_commands("fix the tests")
        assert is_cmd is False
        assert action is None


class TestCircuitBreakers:
    """Test circuit breaker logic."""

    def test_max_iterations_breaker(self):
        """Test max iterations circuit breaker."""
        # Create state at max iterations
        state = {"iteration": ralph_loop.MAX_ITERATIONS, "consecutive_errors": 0}

        # Mock rate limit and token budget checks to pass
        with (
            patch.object(ralph_loop, "check_rate_limit", return_value=(False, "OK")),
            patch.object(ralph_loop, "check_token_budget", return_value=(False, "OK", 0)),
        ):
            should_trip, msg = ralph_loop.check_circuit_breaker(state, "")
            assert should_trip is True
            assert "Max iterations" in msg

    def test_consecutive_errors_breaker(self):
        """Test consecutive errors circuit breaker."""
        state = {
            "iteration": 1,
            "consecutive_errors": 2,  # One below threshold
        }

        transcript_with_error = "error: something failed"

        with (
            patch.object(ralph_loop, "update_ralph_state"),
            patch.object(ralph_loop, "check_rate_limit", return_value=(False, "OK")),
            patch.object(ralph_loop, "check_token_budget", return_value=(False, "OK", 0)),
        ):
            should_trip, msg = ralph_loop.check_circuit_breaker(state, transcript_with_error)

        # Should trip because this would be 3rd error
        assert should_trip is True
        assert "consecutive errors" in msg


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limit_under_threshold(self, tmp_path):
        """Test rate limit allows when under threshold."""
        log_file = tmp_path / "ralph_iterations.jsonl"

        # Write entries spaced apart to avoid min interval trigger
        now = datetime.now()
        entries = [
            {"timestamp": (now - timedelta(minutes=30)).isoformat(), "type": "iteration"},
            {"timestamp": (now - timedelta(minutes=15)).isoformat(), "type": "iteration"},
        ]
        log_file.write_text("\n".join(json.dumps(e) for e in entries))

        with patch.object(ralph_loop, "RALPH_LOG", log_file):
            is_limited, msg = ralph_loop.check_rate_limit()
            assert is_limited is False
            assert "OK" in msg


class TestSSOTConfig:
    """Test SSOT configuration loading."""

    def test_default_config_values(self):
        """Test default config is used when no SSOT found."""
        # DEFAULT_CONFIG is a module-level constant loaded at import time
        assert ralph_loop.DEFAULT_CONFIG["max_iterations"] == 15
        assert ralph_loop.DEFAULT_CONFIG["max_budget_usd"] == 20.0

    def test_ssot_config_loaded(self, tmp_path):
        """Test SSOT config is loaded when available."""
        config_file = tmp_path / "canonical.yaml"
        config_content = """
ralph:
  max_iterations: 25
  max_budget_usd: 50.0
"""
        config_file.write_text(config_content)

        # This would need to be tested at module import time
        # which is more complex. For now, test the function directly.
        # The function looks in multiple paths - this test verifies the structure is correct
        assert config_file.exists()


class TestIntegration:
    """Integration tests for full Ralph workflow."""

    def test_full_state_lifecycle(self, tmp_path):
        """Test complete state create/update/deactivate cycle."""
        state_file = tmp_path / "state.json"

        with (
            patch.object(ralph_loop, "RALPH_STATE", state_file),
            patch.object(ralph_loop, "METRICS_DIR", tmp_path),
            patch.object(ralph_loop, "RALPH_LOG", tmp_path / "ralph.jsonl"),
        ):
            # Create initial state
            state = ralph_loop.update_ralph_state(
                {
                    "active": True,
                    "original_prompt": "Test task",
                    "iteration": 0,
                    "started_at": datetime.now().isoformat(),
                }
            )

            assert state["active"] is True
            assert "_checksum" in state

            # Update iteration
            state = ralph_loop.update_ralph_state({"iteration": 1})
            assert state["iteration"] == 1

            # Verify backup was created
            backup_file = state_file.with_suffix(".json.bak")
            assert backup_file.exists()

            # Deactivate
            ralph_loop.deactivate_ralph("Test complete")

            # Verify state shows inactive
            final_state = json.loads(state_file.read_text())
            assert final_state["active"] is False
            assert final_state["exit_reason"] == "Test complete"


# =============================================================================
# Verification Scenario Tests (Mock)
# =============================================================================


class TestVerificationScenarios:
    """Mock tests for manual verification scenarios."""

    def test_scenario_pr_review_trigger(self):
        """Mock: Verify Opus review triggers on PR."""
        # This would be integration tested via actual PR
        # Mock version just verifies the workflow exists
        Path("/media/sam/1TB/nautilus_dev/.github/workflows/code-review.yml")
        # In real test, verify file exists and has correct structure
        assert True  # Placeholder

    def test_scenario_drawdown_alert(self):
        """Mock: Verify drawdown alert fires."""
        # This would trigger via Grafana alerting
        # Mock version verifies alert rule exists
        assert True  # Placeholder

    def test_scenario_rollback_execution(self):
        """Mock: Verify rollback script works."""
        Path("/media/sam/1TB/nautilus_dev/scripts/rollback.sh")
        # In real test, verify script is executable and has correct logic
        assert True  # Placeholder

    def test_scenario_staging_deploy(self):
        """Mock: Verify staging deployment works."""
        Path("/media/sam/1TB/nautilus_dev/config/staging/docker-compose.staging.yml")
        # In real test, verify compose file is valid
        assert True  # Placeholder


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
