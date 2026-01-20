#!/usr/bin/env python3
"""File Release Hook - PostToolUse hook for Write|Edit|MultiEdit tools.

This hook releases file claims after edit operations complete and broadcasts
a notification to other agents that the file is now available.

Hook type: PostToolUse
Matcher: Write|Edit|MultiEdit

Usage:
  echo '{"tool_input": {"file_path": "/path/to/file"}}' | file_release.py

Returns:
  {} - Always returns empty (no output modification needed)
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
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
            f.write(f"{timestamp} - [file_release] {msg}\n")
    except Exception:
        pass


def get_session_id() -> str:
    """Get session ID from file."""
    session_file = LOG_DIR / "session_id"

    if session_file.exists():
        try:
            return session_file.read_text().strip()
        except Exception:
            pass

    return "unknown"


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


def release_file(file_path: str, session_id: str) -> bool:
    """Release a file claim via claude-flow claims system.

    Returns:
        bool: True if release successful
    """
    issue_id = f"file:{file_path}"
    claimant = f"agent:{session_id}:editor"

    try:
        cmd = [
            "npx",
            "-y",
            "claude-flow@latest",
            "claims",
            "release",
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

        if result.returncode == 0:
            log(f"Released file: {file_path}")
            return True
        else:
            output = result.stdout.strip() or result.stderr.strip()
            log(f"Release failed: {output}")
            return False

    except subprocess.TimeoutExpired:
        log(f"Release timed out for: {file_path}")
        return False
    except Exception as e:
        log(f"Release error for {file_path}: {e}")
        return False


def broadcast_release(file_path: str) -> bool:
    """Broadcast file release notification to other agents.

    Returns:
        bool: True if broadcast successful
    """
    try:
        message = f"File released: {file_path}"
        data = json.dumps({"file": file_path, "event": "release"})

        cmd = [
            "npx",
            "-y",
            "claude-flow@latest",
            "hooks",
            "notify",
            "--message",
            message,
            "--target",
            "all",
            "--data",
            data,
        ]

        log(f"Broadcasting: {message}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(Path.home()),
        )

        if result.returncode == 0:
            log(f"Broadcast successful for: {file_path}")
            return True
        else:
            output = result.stdout.strip() or result.stderr.strip()
            log(f"Broadcast failed: {output}")
            return False

    except subprocess.TimeoutExpired:
        log(f"Broadcast timed out for: {file_path}")
        return False
    except Exception as e:
        log(f"Broadcast error for {file_path}: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="File Release Hook (PostToolUse)")
    parser.add_argument(
        "--event",
        default="release",
        help="Event type (default: release)",
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
            log("No file_path found in tool_input")
            print(json.dumps({}))
            return 0

        session_id = get_session_id()
        state = load_state()

        # Check if we have this file in our claims
        if file_path not in state.get("claimed_files", {}):
            log(f"File not in our claims, skipping release: {file_path}")
            print(json.dumps({}))
            return 0

        # Release the claim
        release_file(file_path, session_id)

        # Broadcast notification (best effort)
        broadcast_release(file_path)

        # Remove from our session state
        if file_path in state["claimed_files"]:
            del state["claimed_files"][file_path]
            save_state(state)
            log(f"Removed {file_path} from session state")

        # Always return empty - don't modify output
        print(json.dumps({}))
        return 0

    except Exception as e:
        log(f"Error in file_release: {e}")
        # On error, still return empty (fail gracefully)
        print(json.dumps({}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
