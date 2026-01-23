#!/usr/bin/env python3
"""
Stop Hook: Ralph Loop Controller

Implements the Ralph Wiggum pattern for continuous autonomous development.
When Claude attempts to stop and Ralph mode is active, this hook:
1. Checks if exit criteria are met (tests pass, no errors)
2. If not met, re-injects the original prompt
3. Tracks progress and applies circuit breakers

Based on: https://ghuntley.com/ralph/

Enterprise Features (v2.0):
- SSOT config loading from canonical.yaml
- State checksum validation
- Structured logging
- Proper error handling (no silent fails)
"""

import asyncio
import fcntl
import json
import logging
import os
import subprocess
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
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "ralph-loop", "message": "%(message)s"}',
    handlers=[
        logging.FileHandler(LOG_DIR / "ralph-loop.log"),
    ],
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration (SSOT)
# =============================================================================

DEFAULT_CONFIG = {
    "max_iterations": 15,
    "max_budget_usd": 20.0,
    "max_consecutive_errors": 3,
    "max_no_progress": 5,
    "max_ci_failures": 3,
    "min_iteration_interval_secs": 10,
    "max_iterations_per_hour": 100,
    "estimated_cost_per_iteration": 2.0,
    "state_path": "~/.claude/ralph/state.json",  # Overridden by get_project_state_path()
    "progress_path": "~/.claude/ralph/progress.md",
}


def get_project_hash() -> str:
    """Generate a short hash from current working directory for project isolation."""
    import hashlib

    cwd = str(Path.cwd().resolve())
    return hashlib.sha256(cwd.encode()).hexdigest()[:12]


def get_project_state_path() -> Path:
    """Get project-specific state path to prevent cross-project interference."""
    project_hash = get_project_hash()
    return Path.home() / ".claude" / "ralph" / f"state_{project_hash}.json"


def get_project_progress_path() -> Path:
    """Get project-specific progress path."""
    project_hash = get_project_hash()
    return Path.home() / ".claude" / "ralph" / f"progress_{project_hash}.md"


def load_ssot_config() -> dict:
    """Load Ralph config from canonical.yaml (SSOT)."""
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

# Paths - PROJECT-SPECIFIC to prevent cross-project interference
RALPH_STATE = get_project_state_path()  # Was global, now per-project
RALPH_PROGRESS = get_project_progress_path()  # Was global, now per-project
METRICS_DIR = Path.home() / ".claude" / "metrics"
RALPH_LOG = METRICS_DIR / "ralph_iterations.jsonl"

# Circuit breaker settings (from SSOT)
MAX_ITERATIONS = CONFIG["max_iterations"]
MAX_CONSECUTIVE_ERRORS = CONFIG["max_consecutive_errors"]
MAX_NO_PROGRESS = CONFIG["max_no_progress"]
MAX_CI_FAILURES = CONFIG["max_ci_failures"]

# Token/cost limits
ESTIMATED_COST_PER_ITERATION = CONFIG["estimated_cost_per_iteration"]
MAX_BUDGET_USD = CONFIG["max_budget_usd"]

# Rate limiting
MAX_ITERATIONS_PER_HOUR = CONFIG["max_iterations_per_hour"]
RATE_LIMIT_WINDOW_SECS = 3600  # 1 hour window
MIN_ITERATION_INTERVAL_SECS = CONFIG["min_iteration_interval_secs"]

# Exit detection patterns
EXIT_PATTERNS = [
    "all tests pass",
    "tests passing",
    "no errors found",
    "task complete",
    "successfully completed",
    "done",
    "finished",
]

ERROR_PATTERNS = [
    "error:",
    "failed",
    "exception",
    "traceback",
    "syntax error",
]


# =============================================================================
# State Management (Enterprise v2.0)
# =============================================================================


def calculate_state_checksum(state: dict) -> str:
    """Calculate checksum for state validation."""
    import hashlib

    state_copy = {k: v for k, v in state.items() if k != "_checksum"}
    state_str = json.dumps(state_copy, sort_keys=True)
    return hashlib.sha256(state_str.encode()).hexdigest()[:16]


def backup_state():
    """Create backup of state before mutation."""
    if RALPH_STATE.exists():
        backup_path = RALPH_STATE.with_suffix(".json.bak")
        try:
            backup_path.write_text(RALPH_STATE.read_text())
            logger.info(f"State backed up to {backup_path}")
        except OSError as e:
            logger.warning(f"Failed to backup state: {e}")


# Plugin state file (markdown with YAML frontmatter)
PLUGIN_STATE_FILE = Path.cwd() / ".claude" / "ralph-loop.local.md"


def parse_plugin_state_file() -> dict | None:
    """
    Parse the official Ralph plugin's state file format.

    Format: Markdown with YAML frontmatter
    ---
    active: true
    iteration: 1
    max_iterations: 20
    completion_promise: "DONE"
    started_at: "2026-01-13T..."
    ---

    The actual prompt text
    """
    if not PLUGIN_STATE_FILE.exists():
        return None

    try:
        content = PLUGIN_STATE_FILE.read_text()

        # Parse YAML frontmatter (between --- markers)
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter = parts[1].strip()
        prompt_text = parts[2].strip()

        # Parse YAML manually (avoid PyYAML dependency)
        state = {"source": "plugin"}
        for line in frontmatter.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                # Type conversion
                if value == "true":
                    value = True
                elif value == "false":
                    value = False
                elif value == "null":
                    value = None
                elif value.isdigit():
                    value = int(value)

                state[key] = value

        # Map plugin fields to our format
        state["original_prompt"] = prompt_text
        state["active"] = state.get("active", False)

        if state.get("active"):
            logger.info(
                f"Loaded state from plugin file: iteration={state.get('iteration', 0)}"
            )
            return state

    except Exception as e:
        logger.warning(f"Failed to parse plugin state file: {e}")

    return None


def get_ralph_state() -> dict | None:
    """
    Get current Ralph state with validation.

    Checks BOTH:
    1. Plugin state file (.claude/ralph-loop.local.md) - from /ralph-loop command
    2. Our state file (~/.claude/ralph/state.json) - from auto-ralph

    Plugin state takes priority if both exist.
    """
    # Check plugin state file FIRST (from /ralph-loop command)
    plugin_state = parse_plugin_state_file()
    if plugin_state:
        return plugin_state

    # Fallback to our state file (from auto-ralph)
    if not RALPH_STATE.exists():
        return None

    try:
        state = json.loads(RALPH_STATE.read_text())
        state["source"] = "auto-ralph"

        # Validate checksum if present
        stored_checksum = state.get("_checksum")
        if stored_checksum:
            calculated = calculate_state_checksum(state)
            if stored_checksum != calculated:
                logger.warning(
                    f"State checksum mismatch: stored={stored_checksum}, calc={calculated}"
                )
                # Continue anyway - might be manual edit

        if state.get("active"):
            return state
    except json.JSONDecodeError as e:
        logger.error(f"State JSON parse error: {e}")
    except OSError as e:
        logger.error(f"State file read error: {e}")

    return None


def update_ralph_state(updates: dict) -> dict:
    """Update Ralph state with new values and checksum."""
    backup_state()

    state = get_ralph_state() or {}
    state.update(updates)
    state["last_activity"] = datetime.now().isoformat()
    state["_checksum"] = calculate_state_checksum(state)

    RALPH_STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        RALPH_STATE.write_text(json.dumps(state, indent=2))
        logger.info(f"State updated: iteration={state.get('iteration', 0)}")
    except OSError as e:
        logger.error(f"Failed to write state: {e}")
        raise

    return state


def deactivate_ralph(reason: str):
    """Deactivate Ralph mode with reason."""
    state = get_ralph_state()
    if not state:
        return

    source = state.get("source", "auto-ralph")

    if source == "plugin":
        # Deactivate plugin state file (delete it, as plugin expects)
        try:
            if PLUGIN_STATE_FILE.exists():
                PLUGIN_STATE_FILE.unlink()
                logger.info(f"Plugin state file removed: {reason}")
        except OSError as e:
            logger.error(f"Failed to remove plugin state file: {e}")
    else:
        # Deactivate our JSON state file
        state["active"] = False
        state["exit_reason"] = reason
        state["ended_at"] = datetime.now().isoformat()
        state["_checksum"] = calculate_state_checksum(state)

        try:
            RALPH_STATE.write_text(json.dumps(state, indent=2))
            logger.info(f"Ralph deactivated: {reason}")
        except OSError as e:
            logger.error(f"Failed to deactivate state: {e}")

    # Log final state
    log_iteration(
        {
            "type": "ralph_exit",
            "reason": reason,
            "source": source,
            "iterations": state.get("iteration", 0) if state else 0,
        }
    )


# =============================================================================
# Progress Tracking
# =============================================================================


def update_progress(iteration: int, summary: str):
    """Update progress markdown file."""
    RALPH_PROGRESS.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    entry = f"""
## Iteration {iteration} ({timestamp})
{summary}
"""

    # Append to progress file
    with open(RALPH_PROGRESS, "a") as f:
        f.write(entry)


def git_commit_progress(iteration: int):
    """Auto-commit progress after each Ralph iteration."""
    try:
        # Check if we're in a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        if result.returncode != 0:
            return  # Not a git repo

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        if not result.stdout.strip():
            return  # No changes

        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            cwd=Path.cwd(),
        )

        # Commit with Ralph iteration info
        commit_msg = f"""[Ralph] Iteration {iteration} checkpoint

Auto-committed by Ralph Loop after iteration {iteration}.
Progress saved to: ~/.claude/ralph/progress.md

🤖 Generated with Claude Code (Ralph Auto-Checkpoint)
Co-Authored-By: Claude <noreply@anthropic.com>"""

        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            cwd=Path.cwd(),
        )
        logger.info(f"Git checkpoint committed for iteration {iteration}")
    except subprocess.SubprocessError as e:
        logger.warning(f"Git commit failed (non-critical): {e}")
    except OSError as e:
        logger.warning(f"Git command error (non-critical): {e}")


def emit_questdb_metric(data: dict):
    """Emit metric to QuestDB via ILP protocol."""
    import socket

    host = os.environ.get("QUESTDB_HOST", "localhost")
    port = int(os.environ.get("QUESTDB_ILP_PORT", "9009"))

    try:
        # ILP line protocol format:
        # ralph_iterations,type=iteration iteration=5i,cost=10.0 timestamp_ns
        tags = f"type={data.get('type', 'unknown')}"
        fields = []

        if "iteration" in data:
            fields.append(f"iteration={data['iteration']}i")
        if "estimated_cost_usd" in data:
            fields.append(f"cost={data['estimated_cost_usd']}")
        if "reason" in data:
            # Escape special chars in string
            reason = data["reason"].replace('"', '\\"').replace("\n", " ")[:100]
            fields.append(f'reason="{reason}"')

        if not fields:
            fields.append("count=1i")

        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = f"ralph_iterations,{tags} {','.join(fields)} {timestamp_ns}\n"

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect((host, port))
            sock.sendall(line.encode())

        logger.info(f"QuestDB metric emitted: {data.get('type', 'unknown')}")
    except OSError as e:
        logger.warning(f"QuestDB emission failed (non-critical): {e}")


def emit_sentry_breadcrumb(data: dict):
    """Add Sentry breadcrumb for debugging context."""
    try:
        import sentry_sdk

        sentry_sdk.add_breadcrumb(
            category="ralph",
            message=f"Ralph {data.get('type', 'event')}: iteration={data.get('iteration', 0)}",
            level="info",
            data=data,
        )
    except ImportError:
        pass  # Sentry not installed
    except Exception as e:
        logger.warning(f"Sentry breadcrumb failed: {e}")


def log_iteration(data: dict):
    """Log Ralph iteration metrics to file, QuestDB, and Sentry."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        **data,
    }

    # File log (always, with lock to prevent race conditions)
    try:
        with open(RALPH_LOG, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry) + "\n")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError as e:
        logger.error(f"Failed to write iteration log: {e}")

    # QuestDB metrics (if available)
    emit_questdb_metric(data)

    # Sentry breadcrumb (if available)
    emit_sentry_breadcrumb(data)


# =============================================================================
# Exit Criteria Checks
# =============================================================================


def check_tests_pass() -> tuple[bool, str]:
    """Check if all tests pass."""
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", "tests/", "-x", "--tb=no", "-q"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            return True, "All tests pass"
        return False, f"Tests failed: {result.stdout[-200:]}"
    except subprocess.TimeoutExpired:
        return False, "Tests timed out"
    except FileNotFoundError:
        # No pytest available, skip check
        return True, "pytest not available (skipped)"
    except Exception as e:
        return False, f"Test check error: {e}"


def check_lint_pass() -> tuple[bool, str]:
    """Check if lint passes."""
    try:
        # Use global ruff config if exists, otherwise default
        global_config = Path.home() / ".claude" / "ruff.toml"
        cmd = ["uv", "run", "ruff", "check", "."]
        if global_config.exists():
            cmd = ["uv", "run", "ruff", "check", ".", "--config", str(global_config)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            return True, "No lint errors"
        errors = len(result.stdout.strip().split("\n")) if result.stdout else 0
        return False, f"Lint errors: {errors}"
    except FileNotFoundError:
        return True, "ruff not available (skipped)"
    except Exception as e:
        return False, f"Lint check error: {e}"


def find_validation_config() -> Path | None:
    """Find validation config in project or templates."""
    candidates = [
        Path.cwd() / ".claude" / "validation" / "config.json",
        Path.cwd() / "config" / "validation.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run_ci_validation() -> tuple[bool, str, dict]:
    """
    Run CI validation between iterations to prevent broken code compounding.

    Phase 7 Enhancement: Uses ValidationOrchestrator for 14-dimension validation
    when config.json exists. Falls back to legacy tests+lint if not.

    Returns:
        (passed, message, details)
    """
    config_path = find_validation_config()

    if config_path:
        # Try orchestrator-based validation
        try:
            orchestrator_path = Path.home() / ".claude" / "templates" / "validation"
            orchestrator_file = orchestrator_path / "orchestrator.py"

            if orchestrator_file.exists():
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "orchestrator", orchestrator_file
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    orchestrator = module.ValidationOrchestrator(config_path)
                    report = asyncio.run(orchestrator.run_all())

                    details = {
                        "source": "orchestrator",
                        "blocked": report.blocked,
                        "execution_time_ms": report.execution_time_ms,
                    }

                    if report.blocked:
                        failed = (
                            report.tiers[0].failed_dimensions if report.tiers else []
                        )
                        return False, f"Tier 1 blocked: {failed}", details

                    logger.info("Validation passed via orchestrator")
                    return True, "Validation passed (orchestrator)", details

        except Exception as e:
            logger.warning(f"Orchestrator error, using legacy: {e}")

    # Legacy validation (original behavior)
    return run_ci_validation_legacy()


def run_ci_validation_legacy() -> tuple[bool, str, dict]:
    """
    Original CI validation - tests + lint only.

    Preserved as fallback when orchestrator is not available.
    """
    details = {"source": "legacy"}

    # Run tests
    tests_ok, tests_msg = check_tests_pass()
    details["tests"] = {"passed": tests_ok, "message": tests_msg}

    # Run lint
    lint_ok, lint_msg = check_lint_pass()
    details["lint"] = {"passed": lint_ok, "message": lint_msg}

    if tests_ok and lint_ok:
        return True, "CI validation passed", details

    # Build failure message
    failures = []
    if not tests_ok:
        failures.append(f"Tests: {tests_msg}")
    if not lint_ok:
        failures.append(f"Lint: {lint_msg}")

    return False, f"CI validation failed: {'; '.join(failures)}", details


def check_exit_criteria(transcript: str) -> tuple[bool, str]:
    """Check if exit criteria are met based on transcript."""
    transcript_lower = transcript.lower()

    # Check for explicit completion signals
    for pattern in EXIT_PATTERNS:
        if pattern in transcript_lower:
            # Verify with actual checks
            tests_ok, tests_msg = check_tests_pass()
            lint_ok, lint_msg = check_lint_pass()

            if tests_ok and lint_ok:
                return True, f"Exit criteria met: {tests_msg}, {lint_msg}"

    return False, "Exit criteria not met"


def check_token_budget(state: dict) -> tuple[bool, str, float]:
    """
    Check if estimated token budget is exceeded.

    Returns:
        (exceeded, message, estimated_cost)
    """
    iteration = state.get("iteration", 0)
    estimated_cost = iteration * ESTIMATED_COST_PER_ITERATION

    if estimated_cost >= MAX_BUDGET_USD:
        return (
            True,
            f"Budget limit ${MAX_BUDGET_USD:.2f} reached (estimated ${estimated_cost:.2f})",
            estimated_cost,
        )

    remaining = MAX_BUDGET_USD - estimated_cost
    return (
        False,
        f"Budget OK: ${estimated_cost:.2f} / ${MAX_BUDGET_USD:.2f} (${remaining:.2f} remaining)",
        estimated_cost,
    )


def check_rate_limit() -> tuple[bool, str]:
    """Check if rate limit is exceeded."""
    if not RALPH_LOG.exists():
        return False, "Rate limit OK"

    try:
        now = datetime.now()
        cutoff = now.timestamp() - RATE_LIMIT_WINDOW_SECS
        iterations_in_window = 0
        last_iteration_time = None

        with open(RALPH_LOG) as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for read
            try:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ts = datetime.fromisoformat(
                            entry.get("timestamp", "")
                        ).timestamp()
                        if ts > cutoff:
                            iterations_in_window += 1
                            if last_iteration_time is None or ts > last_iteration_time:
                                last_iteration_time = ts
                    except (json.JSONDecodeError, ValueError):
                        continue
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Check max iterations per hour
        if iterations_in_window >= MAX_ITERATIONS_PER_HOUR:
            return (
                True,
                f"Rate limit: {iterations_in_window} iterations in last hour (max {MAX_ITERATIONS_PER_HOUR})",
            )

        # Check min interval between iterations
        if last_iteration_time:
            elapsed = now.timestamp() - last_iteration_time
            if elapsed < MIN_ITERATION_INTERVAL_SECS:
                return (
                    True,
                    f"Rate limit: {elapsed:.0f}s since last iteration (min {MIN_ITERATION_INTERVAL_SECS}s)",
                )

    except OSError as e:
        logger.warning(f"Rate limit check failed (allowing): {e}")
    except Exception as e:
        logger.warning(f"Unexpected rate limit error (allowing): {e}")

    return False, "Rate limit OK"


def check_circuit_breaker(state: dict, transcript: str) -> tuple[bool, str]:
    """Check if circuit breaker should trip."""
    iteration = state.get("iteration", 0)

    # Rate limit check
    rate_limited, rate_msg = check_rate_limit()
    if rate_limited:
        return True, rate_msg

    # Token budget check
    budget_exceeded, budget_msg, _ = check_token_budget(state)
    if budget_exceeded:
        return True, budget_msg

    # Max iterations
    if iteration >= MAX_ITERATIONS:
        return True, f"Max iterations reached ({MAX_ITERATIONS})"

    # Consecutive errors
    transcript_lower = transcript.lower()
    has_error = any(pattern in transcript_lower for pattern in ERROR_PATTERNS)

    if has_error:
        consecutive_errors = state.get("consecutive_errors", 0) + 1
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            return True, f"Too many consecutive errors ({consecutive_errors})"
        update_ralph_state({"consecutive_errors": consecutive_errors})
    else:
        update_ralph_state({"consecutive_errors": 0})

    # No progress detection (same output twice)
    last_summary = state.get("last_summary", "")
    current_summary = transcript[-500:]  # Last 500 chars as summary

    if current_summary == last_summary:
        no_progress = state.get("consecutive_no_progress", 0) + 1
        if no_progress >= MAX_NO_PROGRESS:
            return True, f"No progress detected ({no_progress} iterations)"
        update_ralph_state({"consecutive_no_progress": no_progress})
    else:
        update_ralph_state(
            {
                "consecutive_no_progress": 0,
                "last_summary": current_summary,
            }
        )

    return False, "Circuit breaker OK"


# =============================================================================
# Main Hook
# =============================================================================


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Get Ralph state
    state = get_ralph_state()

    if not state:
        # Ralph not active, allow normal exit
        print(json.dumps({}))
        sys.exit(0)

    # Get transcript summary from stop reason
    stop_reason = input_data.get("stopReason", "")
    transcript = input_data.get("transcript", "")

    # Update iteration count
    iteration = state.get("iteration", 0) + 1
    update_ralph_state({"iteration": iteration})

    # Check budget status
    _, budget_status, estimated_cost = check_token_budget(state)

    # Check circuit breaker BEFORE logging (to avoid rate limit self-trigger)
    should_trip, trip_msg = check_circuit_breaker(state, transcript)

    # Log iteration (AFTER circuit breaker check)
    log_iteration(
        {
            "type": "iteration",
            "iteration": iteration,
            "stop_reason": stop_reason[:100],
            "estimated_cost_usd": estimated_cost,
            "circuit_breaker_tripped": should_trip,
        }
    )

    # Check exit criteria
    should_exit, exit_msg = check_exit_criteria(transcript)
    if should_exit:
        deactivate_ralph(exit_msg)
        update_progress(iteration, f"✅ COMPLETED: {exit_msg}")
        git_commit_progress(iteration)

        # Allow exit - Ralph complete
        output = {
            "decision": "approve",
            "stopReason": f"🏁 Ralph Loop Complete (iteration {iteration}): {exit_msg}",
        }
        print(json.dumps(output))
        sys.exit(0)

    # Handle circuit breaker (now checked above)
    if should_trip:
        deactivate_ralph(trip_msg)
        update_progress(iteration, f"⚠️ CIRCUIT BREAKER: {trip_msg}")
        git_commit_progress(iteration)

        # Allow exit - circuit breaker tripped
        output = {
            "decision": "approve",
            "stopReason": f"⚠️ Ralph Loop Stopped (circuit breaker): {trip_msg}",
        }
        print(json.dumps(output))
        sys.exit(0)

    # Run CI validation between iterations (prevent broken code compounding)
    ci_passed, ci_msg, ci_details = run_ci_validation()

    if not ci_passed:
        ci_failures = state.get("consecutive_ci_failures", 0) + 1
        update_ralph_state({"consecutive_ci_failures": ci_failures})

        log_iteration(
            {
                "type": "ci_failure",
                "iteration": iteration,
                "details": ci_details,
            }
        )

        if ci_failures >= MAX_CI_FAILURES:
            deactivate_ralph(f"CI failed {ci_failures} times consecutively")
            update_progress(
                iteration,
                f"⚠️ CI FAILURE CIRCUIT BREAKER: {ci_msg}\nFix the issues before continuing.",
            )
            git_commit_progress(iteration)

            # Allow exit - CI failures exceeded
            output = {
                "decision": "approve",
                "stopReason": f"⚠️ Ralph Loop Stopped (CI failures): {ci_msg}",
            }
            print(json.dumps(output))
            sys.exit(0)

        # CI failed but not max yet - include fix instructions in continuation
        update_progress(
            iteration, f"⚠️ CI FAILED ({ci_failures}/{MAX_CI_FAILURES}): {ci_msg}"
        )
    else:
        # CI passed - reset counter
        update_ralph_state({"consecutive_ci_failures": 0})

    # Continue loop - re-inject original prompt
    original_prompt = state.get("original_prompt", "")

    update_progress(iteration, f"Iteration {iteration} - continuing...")
    git_commit_progress(iteration)

    # Build CI status section (compact)
    if ci_passed:
        ci_status = "✅ CI OK"
    else:
        ci_failures = state.get("consecutive_ci_failures", 1)
        ci_status = f"""⚠️ CI FAILED ({ci_failures}/{MAX_CI_FAILURES}) - Fix first!
{ci_msg}"""

    # Build continuation message (compact for Max subscription)
    continuation_prompt = f"""## Ralph Loop [{iteration}/{MAX_ITERATIONS}]

{ci_status}

**Task:** {original_prompt}

Continue until CI passes or state "DONE".
"""

    # Stop hook output format (per Claude Code schema):
    # - decision: "block" to prevent exit and continue
    # - reason: The prompt to re-inject
    # - systemMessage: Status shown to user
    ci_status_short = "✅" if ci_passed else "⚠️"
    output = {
        "decision": "block",
        "reason": continuation_prompt,
        "systemMessage": f"🔄 Ralph [{iteration}/{MAX_ITERATIONS}] CI: {ci_status_short}",
    }

    print(json.dumps(output))
    sys.exit(0)  # Exit 0 with decision=block


if __name__ == "__main__":
    main()
