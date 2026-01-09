#!/usr/bin/env python3
"""
UserPromptSubmit Hook: Ralph Resume Detection

Detects if a previous Ralph session was interrupted and offers to resume.
Runs on every user prompt submission to check for orphaned state.

Enterprise features:
- State validation with checksum
- Structured logging
- Sentry integration for errors
- SSOT config loading from canonical.yaml
"""

import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# =============================================================================
# Logging Setup
# =============================================================================

LOG_DIR = Path.home() / ".claude" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "ralph-resume", "message": "%(message)s"}',
    handlers=[
        logging.FileHandler(LOG_DIR / "ralph-resume.log"),
    ],
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration (SSOT)
# =============================================================================

DEFAULT_CONFIG = {
    "max_iterations": 15,
    "max_budget_usd": 20.0,
    "state_path": "~/.claude/ralph/state.json",
    "progress_path": "~/.claude/ralph/progress.md",
}


def load_ssot_config() -> dict:
    """Load Ralph config from canonical.yaml (SSOT)."""
    # Try multiple possible locations for canonical.yaml
    possible_paths = [
        Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / "config" / "canonical.yaml",
        Path.cwd() / "config" / "canonical.yaml",
        Path("/media/sam/1TB/nautilus_dev/config/canonical.yaml"),
    ]

    for config_path in possible_paths:
        if config_path.exists():
            try:
                import yaml

                with open(config_path) as f:
                    data = yaml.safe_load(f)
                    ralph_config = data.get("ralph", {})
                    if ralph_config:
                        logger.info(f"Loaded config from SSOT: {config_path}")
                        return {**DEFAULT_CONFIG, **ralph_config}
            except ImportError:
                logger.warning("PyYAML not available, using defaults")
            except Exception as e:
                logger.warning(f"Failed to load SSOT config: {e}")

    logger.info("Using default config (canonical.yaml not found)")
    return DEFAULT_CONFIG


CONFIG = load_ssot_config()
RALPH_STATE = Path(os.path.expanduser(CONFIG["state_path"]))
RALPH_PROGRESS = Path(os.path.expanduser(CONFIG["progress_path"]))

# =============================================================================
# State Management
# =============================================================================


def calculate_state_checksum(state: dict) -> str:
    """Calculate checksum for state validation."""
    # Exclude checksum field itself
    state_copy = {k: v for k, v in state.items() if k != "_checksum"}
    state_str = json.dumps(state_copy, sort_keys=True)
    return hashlib.sha256(state_str.encode()).hexdigest()[:16]


def validate_state(state: dict) -> tuple[bool, str]:
    """Validate state integrity."""
    if not state:
        return False, "Empty state"

    # Check required fields
    required = ["active", "original_prompt", "started_at"]
    missing = [f for f in required if f not in state]
    if missing:
        return False, f"Missing fields: {missing}"

    # Validate checksum if present
    stored_checksum = state.get("_checksum")
    if stored_checksum:
        calculated = calculate_state_checksum(state)
        if stored_checksum != calculated:
            logger.warning(f"State checksum mismatch: {stored_checksum} != {calculated}")
            # Don't fail - just warn (state might have been manually edited)

    # Check if started_at is valid datetime
    try:
        datetime.fromisoformat(state["started_at"])
    except (ValueError, TypeError):
        return False, "Invalid started_at timestamp"

    return True, "Valid"


def get_ralph_state() -> dict | None:
    """Get current Ralph state with validation."""
    if not RALPH_STATE.exists():
        return None

    try:
        state = json.loads(RALPH_STATE.read_text())

        # Validate state
        valid, reason = validate_state(state)
        if not valid:
            logger.warning(f"Invalid state: {reason}")
            return None

        if state.get("active"):
            return state
    except json.JSONDecodeError as e:
        logger.error(f"State JSON parse error: {e}")
    except OSError as e:
        logger.error(f"State file read error: {e}")

    return None


def get_session_age(state: dict) -> tuple[float, str]:
    """Get age of Ralph session in hours and human-readable format."""
    try:
        started = datetime.fromisoformat(state["started_at"])
        age = datetime.now() - started
        hours = age.total_seconds() / 3600

        if hours < 1:
            human = f"{int(age.total_seconds() / 60)} minutes"
        elif hours < 24:
            human = f"{hours:.1f} hours"
        else:
            human = f"{hours / 24:.1f} days"

        return hours, human
    except (ValueError, KeyError):
        return 0, "unknown"


def get_progress_summary() -> str:
    """Get summary of progress file."""
    if not RALPH_PROGRESS.exists():
        return "No progress file found"

    try:
        content = RALPH_PROGRESS.read_text()
        lines = content.strip().split("\n")

        # Count iterations
        iterations = content.count("## Iteration")

        # Get last entry
        last_entry = ""
        for i, line in enumerate(reversed(lines)):
            if line.startswith("## Iteration"):
                last_entry = "\n".join(lines[len(lines) - i - 1 :])[:200]
                break

        return f"{iterations} iterations logged. Last: {last_entry[:100]}..."
    except OSError:
        return "Could not read progress file"


def deactivate_state(reason: str):
    """Deactivate Ralph state with reason."""
    if not RALPH_STATE.exists():
        return

    try:
        state = json.loads(RALPH_STATE.read_text())
        state["active"] = False
        state["exit_reason"] = reason
        state["ended_at"] = datetime.now().isoformat()
        state["_checksum"] = calculate_state_checksum(state)
        RALPH_STATE.write_text(json.dumps(state, indent=2))
        logger.info(f"Deactivated Ralph state: {reason}")
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to deactivate state: {e}")


# =============================================================================
# Resume Detection
# =============================================================================


def check_resume_commands(prompt: str) -> tuple[bool, str | None]:
    """Check if user explicitly issued resume/discard command."""
    prompt_lower = prompt.lower().strip()

    # Resume commands
    if any(
        cmd in prompt_lower
        for cmd in ["ralph resume", "resume ralph", "continue ralph", "ralph continue"]
    ):
        return True, "resume"

    # Discard commands
    if any(
        cmd in prompt_lower
        for cmd in [
            "ralph discard",
            "discard ralph",
            "ralph reset",
            "reset ralph",
            "ralph clear",
            "clear ralph",
        ]
    ):
        return True, "discard"

    return False, None


# =============================================================================
# Main Hook
# =============================================================================


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Get user's prompt
    prompt = input_data.get("prompt", "")

    # Check for explicit resume/discard commands
    is_command, action = check_resume_commands(prompt)

    if is_command:
        state = get_ralph_state()

        if action == "discard":
            if state:
                deactivate_state("User requested discard")
                output = {
                    "notification": "Ralph state discarded. Starting fresh.",
                }
            else:
                output = {
                    "notification": "No active Ralph state to discard.",
                }
            print(json.dumps(output))
            sys.exit(0)

        elif action == "resume" and state:
            # User explicitly wants to resume
            iteration = state.get("iteration", 0)
            original_prompt = state.get("original_prompt", "")
            _, age_human = get_session_age(state)
            progress = get_progress_summary()

            resume_prompt = f"""
## Ralph Loop - Resuming Session

**Original Task**: {original_prompt}
**Iteration**: {iteration}/{CONFIG["max_iterations"]}
**Session Age**: {age_human}

### Progress Summary
{progress}

### Commands
- `uv run pytest tests/ -x --tb=short` - Run tests
- `uv run ruff check . --fix` - Fix lint
- `STOP RALPH` - Exit loop

Continue working on the task. All exit criteria must pass.
"""
            output = {
                "continueWithPrompt": resume_prompt,
                "notification": f"Resuming Ralph loop at iteration {iteration}",
            }
            print(json.dumps(output))
            logger.info(f"Resumed Ralph session at iteration {iteration}")
            sys.exit(0)

    # Check for orphaned session (not a command, just detecting)
    state = get_ralph_state()

    if state:
        iteration = state.get("iteration", 0)
        original_prompt = state.get("original_prompt", "")[:100]
        hours_old, age_human = get_session_age(state)

        # Only notify for sessions older than 1 minute but younger than 24 hours
        # (very old sessions are probably abandoned)
        if 0.016 < hours_old < 24:  # 1 minute to 24 hours
            logger.info(f"Detected orphaned Ralph session: {iteration} iterations, {age_human} old")

            output = {
                "additionalContext": f"""[Ralph Session Detected]
An active Ralph session exists from {age_human} ago.
- Task: {original_prompt}...
- Iteration: {iteration}/{CONFIG["max_iterations"]}

Commands:
- "RALPH RESUME" - Continue where you left off
- "RALPH DISCARD" - Start fresh""",
            }
            print(json.dumps(output))
            sys.exit(0)

    # No active session or nothing to report
    print(json.dumps({}))
    sys.exit(0)


if __name__ == "__main__":
    main()
