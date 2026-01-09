#!/usr/bin/env python3
"""
Hook Health Manager - Self-Healing Hooks Infrastructure

Tracks hook failures and auto-disables hooks that fail repeatedly.
Provides circuit breaker pattern for Claude Code hooks.

USAGE:
    from hook_health import HookHealth

    health = HookHealth("my-hook-name")

    # Check if hook should run
    if health.is_disabled():
        sys.exit(0)  # Skip execution

    # At the end, report result
    health.report_success()  # or
    health.report_failure("error message")

CONFIGURATION:
    Thresholds defined in this module:
    - MAX_FAILURES: 3 failures before disable
    - FAILURE_WINDOW_SECONDS: 300 (5 min) - failures must occur within this window
    - DISABLE_DURATION_SECONDS: 3600 (1 hour) - how long to disable

STATE FILE:
    ~/.claude/metrics/hook_health.json
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import threading

# Configuration
MAX_FAILURES = 3
FAILURE_WINDOW_SECONDS = 300  # 5 minutes
DISABLE_DURATION_SECONDS = 3600  # 1 hour
STATE_FILE = Path.home() / ".claude" / "metrics" / "hook_health.json"

# Thread safety
_lock = threading.Lock()


def _ensure_state_dir():
    """Ensure state directory exists."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    """Load hook health state from file."""
    if not STATE_FILE.exists():
        return {"hooks": {}, "disabled_until": {}}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"hooks": {}, "disabled_until": {}}


def _save_state(state: dict):
    """Save hook health state to file (atomic)."""
    _ensure_state_dir()
    temp_file = STATE_FILE.with_suffix(".tmp")
    try:
        with open(temp_file, "w") as f:
            json.dump(state, f, indent=2, default=str)
        temp_file.replace(STATE_FILE)
    except OSError:
        pass


class HookHealth:
    """Hook health tracker with circuit breaker pattern."""

    def __init__(self, hook_name: str):
        """Initialize with hook name."""
        self.hook_name = hook_name
        self._state = None

    def _get_state(self) -> dict:
        """Get current state (lazy load)."""
        if self._state is None:
            with _lock:
                self._state = _load_state()
        return self._state

    def is_disabled(self) -> bool:
        """
        Check if this hook is currently disabled.

        Returns True if hook should skip execution.
        """
        state = self._get_state()
        disabled_until = state.get("disabled_until", {}).get(self.hook_name)

        if disabled_until:
            disabled_time = datetime.fromisoformat(disabled_until)
            if datetime.now() < disabled_time:
                return True
            else:
                # Disable period expired, re-enable
                with _lock:
                    state["disabled_until"].pop(self.hook_name, None)
                    _save_state(state)

        return False

    def get_disable_reason(self) -> Optional[str]:
        """Get reason for disable if disabled."""
        state = self._get_state()
        hook_data = state.get("hooks", {}).get(self.hook_name, {})
        return hook_data.get("last_error")

    def report_success(self):
        """Report successful hook execution. Clears failure history."""
        with _lock:
            state = self._get_state()
            if self.hook_name in state.get("hooks", {}):
                # Clear failures on success
                state["hooks"][self.hook_name] = {
                    "failures": [],
                    "last_success": datetime.now().isoformat(),
                    "total_successes": state["hooks"].get(self.hook_name, {}).get("total_successes", 0) + 1
                }
                _save_state(state)

    def report_failure(self, error: str = None):
        """
        Report hook failure. May trigger auto-disable.

        Returns True if hook was disabled as a result.
        """
        with _lock:
            state = self._get_state()

            if "hooks" not in state:
                state["hooks"] = {}
            if "disabled_until" not in state:
                state["disabled_until"] = {}

            if self.hook_name not in state["hooks"]:
                state["hooks"][self.hook_name] = {"failures": [], "total_successes": 0}

            hook_data = state["hooks"][self.hook_name]

            # Add this failure
            now = datetime.now()
            hook_data["failures"].append({
                "timestamp": now.isoformat(),
                "error": error[:200] if error else None
            })
            hook_data["last_error"] = error[:200] if error else "Unknown error"

            # Remove failures outside the window
            cutoff = now - timedelta(seconds=FAILURE_WINDOW_SECONDS)
            hook_data["failures"] = [
                f for f in hook_data["failures"]
                if datetime.fromisoformat(f["timestamp"]) > cutoff
            ]

            # Check if should disable
            if len(hook_data["failures"]) >= MAX_FAILURES:
                disable_until = now + timedelta(seconds=DISABLE_DURATION_SECONDS)
                state["disabled_until"][self.hook_name] = disable_until.isoformat()

                # Log the disable event
                self._log_disable_event(error)

                _save_state(state)
                return True

            _save_state(state)
            return False

    def _log_disable_event(self, error: str = None):
        """Log hook disable event to QuestDB."""
        try:
            scripts_dir = Path(__file__).parent
            sys.path.insert(0, str(scripts_dir))
            from questdb_metrics import QuestDBMetrics

            writer = QuestDBMetrics()
            writer.log_event(
                session_id="system",
                event_type="hook_disabled",
                tool_name=self.hook_name,
                error_message=f"Auto-disabled after {MAX_FAILURES} failures: {error or 'unknown'}",
                severity="high"
            )
        except Exception:
            pass  # Don't fail on logging

    def force_enable(self):
        """Force re-enable this hook (manual override)."""
        with _lock:
            state = self._get_state()
            state.get("disabled_until", {}).pop(self.hook_name, None)
            if self.hook_name in state.get("hooks", {}):
                state["hooks"][self.hook_name]["failures"] = []
            _save_state(state)

    @staticmethod
    def get_all_disabled() -> dict:
        """Get all currently disabled hooks."""
        state = _load_state()
        now = datetime.now()
        disabled = {}

        for hook_name, until_str in state.get("disabled_until", {}).items():
            until = datetime.fromisoformat(until_str)
            if until > now:
                remaining = (until - now).total_seconds()
                disabled[hook_name] = {
                    "disabled_until": until_str,
                    "remaining_minutes": round(remaining / 60, 1),
                    "reason": state.get("hooks", {}).get(hook_name, {}).get("last_error")
                }

        return disabled

    @staticmethod
    def enable_all():
        """Re-enable all disabled hooks."""
        with _lock:
            state = _load_state()
            state["disabled_until"] = {}
            _save_state(state)


def check_hook_health(hook_name: str) -> bool:
    """
    Quick check if hook should run.

    Returns True if hook should execute, False if disabled.
    """
    return not HookHealth(hook_name).is_disabled()


# CLI for manual management
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hook Health Manager")
    parser.add_argument("--list", action="store_true", help="List disabled hooks")
    parser.add_argument("--enable", type=str, help="Enable specific hook")
    parser.add_argument("--enable-all", action="store_true", help="Enable all hooks")
    parser.add_argument("--status", type=str, help="Get status of specific hook")

    args = parser.parse_args()

    if args.list:
        disabled = HookHealth.get_all_disabled()
        if disabled:
            print("Disabled hooks:")
            for name, info in disabled.items():
                print(f"  {name}:")
                print(f"    Remaining: {info['remaining_minutes']} min")
                print(f"    Reason: {info['reason']}")
        else:
            print("No hooks disabled")

    elif args.enable:
        HookHealth(args.enable).force_enable()
        print(f"Hook '{args.enable}' enabled")

    elif args.enable_all:
        HookHealth.enable_all()
        print("All hooks enabled")

    elif args.status:
        health = HookHealth(args.status)
        if health.is_disabled():
            print(f"Hook '{args.status}' is DISABLED")
            print(f"Reason: {health.get_disable_reason()}")
        else:
            print(f"Hook '{args.status}' is ENABLED")
    else:
        parser.print_help()
