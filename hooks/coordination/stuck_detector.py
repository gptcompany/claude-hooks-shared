#!/usr/bin/env python3
"""Stuck Detector Hook - Marks active claims as stealable on session end.

Stop hook that runs when a session ends. It ensures any claims held by this
session are marked as stealable so other agents can take over the work.

Hook type: Stop

Usage:
  # As Stop hook (receives JSON from stdin)
  echo '{}' | python3 stuck_detector.py

  # Direct test
  python3 stuck_detector.py --help
  python3 stuck_detector.py --dry-run
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "coordination.log"
SESSION_STATE_FILE = LOG_DIR / "session_state.json"
CLAIMS_STORE_FILE = Path.home() / ".claude-flow" / "claims" / "claims.json"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def log_msg(msg: str) -> None:
    """Log message to coordination log."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} - stuck_detector - {msg}\n")
    except Exception:
        pass


def load_claims_store() -> dict:
    """Load claims store from file, ensuring correct structure."""
    CLAIMS_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    default = {"claims": {}, "stealable": {}, "contests": {}}
    if not CLAIMS_STORE_FILE.exists():
        CLAIMS_STORE_FILE.write_text(json.dumps(default))
        return default
    try:
        data = json.loads(CLAIMS_STORE_FILE.read_text())
        return {k: data.get(k, {}) for k in default}
    except Exception as e:
        logger.error(f"Load claims store error: {e}")
        return default


def save_claims_store(data: dict) -> None:
    """Save claims store to file."""
    CLAIMS_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CLAIMS_STORE_FILE.write_text(json.dumps(data, indent=2))


def normalize_claimant(claimant) -> str:
    """Convert claimant to string format."""
    if isinstance(claimant, dict):
        return f"{claimant.get('type', '')}:{claimant.get('agentId', '')}:{claimant.get('agentType', '')}"
    return str(claimant) if claimant else ""


def on_stop(hook_input: dict, dry_run: bool = False) -> dict:
    """Handle Stop event - mark all active claims as stealable.

    This ensures that when a session ends (normally or abnormally),
    any claims it was holding become available for other agents to steal.
    """
    log_msg("Stop hook triggered - checking for active claims")

    # Load session state
    if not SESSION_STATE_FILE.exists():
        log_msg("No session state found - nothing to clean up")
        return {}

    try:
        session_state = json.loads(SESSION_STATE_FILE.read_text())
    except Exception as e:
        logger.error(f"Failed to load session state: {e}")
        return {}

    session_id = session_state.get("session_id")
    if not session_id:
        log_msg("No session_id in state - nothing to clean up")
        return {}

    log_msg(f"Processing session: {session_id}")

    # Get active claims for this session and mark them stealable
    store = load_claims_store()
    claimant_prefix = f"agent:{session_id}"
    marked_count = 0

    for issue_id, claim in list(store["claims"].items()):
        claimant_str = normalize_claimant(claim.get("claimant", ""))
        if not claimant_str.startswith(claimant_prefix):
            continue
        if claim.get("status", "active") != "active":
            continue

        if dry_run:
            log_msg(f"[DRY RUN] Would mark stealable: {issue_id}")
        else:
            store["stealable"][issue_id] = {
                **claim,
                "status": "stealable",
                "stealReason": "blocked-timeout",
                "stealContext": "Session ended with active claim - stuck detector",
                "markedStealableAt": datetime.now(timezone.utc).isoformat(),
                "availableFor": "any",
            }
            del store["claims"][issue_id]
            logger.info(f"Marked claim stealable: {issue_id}")
        marked_count += 1

    if marked_count == 0:
        log_msg(f"No active claims for session {session_id}")
    else:
        log_msg(f"Marked {marked_count} claim(s) as stealable")
        if not dry_run:
            save_claims_store(store)

    # Clear session state file
    if not dry_run:
        try:
            SESSION_STATE_FILE.unlink()
            logger.info("Cleared session state file")
        except Exception as e:
            logger.error(f"Failed to clear session state: {e}")

    log_msg("Stop hook completed")
    return {}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Stuck Detector Hook - marks active claims as stealable on Stop")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually mark claims, just log what would happen",
    )
    parser.add_argument("--test", action="store_true", help="Run in test mode with sample data")
    args = parser.parse_args()

    # Read hook input from stdin
    hook_input = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                hook_input = json.loads(raw)
        except json.JSONDecodeError:
            pass

    # Run the stop handler - Stop hooks should NEVER fail
    try:
        result = on_stop(hook_input, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Error in stuck_detector: {e}")
        log_msg(f"ERROR: {e}")
        result = {}

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
