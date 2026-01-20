#!/usr/bin/env python3
"""File Claim Hook - PreToolUse hook for Write|Edit|MultiEdit tools.

This hook claims files before edit operations to prevent conflicts when
multiple agents work in parallel. If a file is already claimed by another
agent, the edit is blocked.

Hook type: PreToolUse
Matcher: Write|Edit|MultiEdit

Usage:
  echo '{"tool_input": {"file_path": "/path/to/file"}}' | file_claim.py

Returns:
  {} - Claim successful, edit may proceed
  {"decision": "block", "reason": "..."} - File claimed by another agent
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Logging
LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "coordination.log"

# Session state file (stores claimed files for this session)
STATE_FILE = LOG_DIR / "file_claims_state.json"


def log(msg: str):
    """Log message to file."""
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(LOG_FILE, "a") as f:
            f.write(f"{timestamp} - [file_claim] {msg}\n")
    except Exception:
        pass


def get_session_id() -> str:
    """Get or create session ID for this session."""
    session_file = LOG_DIR / "session_id"

    if session_file.exists():
        try:
            return session_file.read_text().strip()
        except Exception:
            pass

    # Generate new session ID
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    with contextlib.suppress(Exception):
        session_file.write_text(session_id)

    return session_id


def load_state() -> dict:
    """Load session state (claimed files)."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"claimed_files": {}}


def save_state(state: dict):
    """Save session state."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"Error saving state: {e}")


def extract_file_path(tool_input: dict) -> str | None:
    """Extract and normalize file path from tool input."""
    # Write tool uses file_path
    file_path = tool_input.get("file_path")

    # Edit tool might use file_path or path
    if not file_path:
        file_path = tool_input.get("path")

    if not file_path:
        return None

    # Normalize to absolute path
    return os.path.abspath(file_path)


def claim_file(file_path: str, session_id: str) -> tuple[bool, str | None]:
    """Claim a file via claude-flow claims system.

    Returns:
        tuple: (success, existing_claimant or error message)
    """
    issue_id = f"file:{file_path}"
    claimant = f"agent:{session_id}:editor"

    try:
        cmd = [
            "npx",
            "-y",
            "claude-flow@latest",
            "claims",
            "claim",
            "--issueId",
            issue_id,
            "--claimant",
            claimant,
        ]

        log(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(Path.home()),
        )

        output = result.stdout.strip() or result.stderr.strip()

        if result.returncode == 0:
            log(f"Claimed file: {file_path}")
            return True, None
        else:
            # Parse error to extract existing claimant
            # claude-flow typically returns info about existing claim
            log(f"Claim failed: {output}")
            return False, output

    except subprocess.TimeoutExpired:
        log(f"Claim timed out for: {file_path}")
        return False, "Claim operation timed out"
    except Exception as e:
        log(f"Claim error for {file_path}: {e}")
        return False, str(e)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="File Claim Hook (PreToolUse)")
    parser.add_argument(
        "--event",
        default="claim",
        help="Event type (default: claim)",
    )
    parser.parse_args()  # Validate args but don't store (unused)

    # Read hook input from stdin
    hook_input = {}
    if not sys.stdin.isatty():
        with contextlib.suppress(json.JSONDecodeError):
            hook_input = json.load(sys.stdin)

    try:
        tool_input = hook_input.get("tool_input", {})
        file_path = extract_file_path(tool_input)

        if not file_path:
            log("No file_path found in tool_input, allowing operation")
            print(json.dumps({}))
            return 0

        session_id = get_session_id()

        # Check if we already have this file claimed in our state
        state = load_state()
        if file_path in state["claimed_files"]:
            # We already have the claim, proceed
            log(f"Already claimed by us: {file_path}")
            print(json.dumps({}))
            return 0

        # Try to claim the file
        success, error = claim_file(file_path, session_id)

        if success:
            # Store in our session state
            state["claimed_files"][file_path] = {
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
            }
            save_state(state)
            print(json.dumps({}))
            return 0
        else:
            # Block the edit - file is claimed by another agent
            reason = f"File is claimed by another agent: {error}"
            log(f"Blocking edit: {reason}")
            result = {
                "decision": "block",
                "reason": reason,
            }
            print(json.dumps(result))
            return 0

    except Exception as e:
        log(f"Error in file_claim: {e}")
        # On error, allow operation to proceed (fail open)
        print(json.dumps({}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
