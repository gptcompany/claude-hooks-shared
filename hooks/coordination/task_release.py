#!/usr/bin/env python3
"""Task Release Hook - SubagentStop hook for releasing task claims.

Releases task claims when a subagent completes and broadcasts completion
to other agents via hooks_notify.

Hook type: SubagentStop (matcher: "")

Usage:
  echo '{"agent_id": "task-abc123"}' | task_release.py

Output: JSON {} (always succeeds)
"""

import argparse
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

# Session state file for tracking active task claims (shared with task_claim.py)
TASK_CLAIMS_FILE = LOG_DIR / "active_task_claims.json"


def get_timestamp() -> str:
    """Get ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


def log(msg: str):
    """Log message to coordination log file."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{get_timestamp()} [task_release] {msg}\n")
    except Exception:
        pass


def get_session_id() -> str:
    """Get session ID from environment or file."""
    if session_id := os.environ.get("CLAUDE_SESSION_ID"):
        return session_id

    session_file = LOG_DIR / "session_id"
    if session_file.exists():
        try:
            return session_file.read_text().strip()
        except Exception:
            pass

    return "unknown-session"


def load_active_claims() -> dict:
    """Load active task claims from state file."""
    if TASK_CLAIMS_FILE.exists():
        try:
            with open(TASK_CLAIMS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"claims": []}


def save_active_claims(claims: dict):
    """Save active task claims to state file."""
    try:
        with open(TASK_CLAIMS_FILE, "w") as f:
            json.dump(claims, f, indent=2)
    except Exception as e:
        log(f"Error saving claims: {e}")


def call_claims_release(issue_id: str, claimant: str) -> dict:
    """Call claude-flow claims_release via CLI.

    Returns dict with success status.
    """
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

        log(f"Releasing claim: {issue_id}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(Path.home()),
        )

        output = result.stdout.strip() or result.stderr.strip()
        success = result.returncode == 0

        if success:
            log(f"Release successful for {issue_id}")
        else:
            log(f"Release failed for {issue_id}: {output[:100]}")

        return {
            "success": success,
            "output": output,
        }

    except subprocess.TimeoutExpired:
        log(f"Release timeout for {issue_id}")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        log(f"Release error for {issue_id}: {e}")
        return {"success": False, "error": str(e)}


def call_hooks_notify(message: str, data: dict) -> dict:
    """Call claude-flow hooks_notify via CLI.

    Broadcasts task completion to all agents.
    """
    try:
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
            "--priority",
            "normal",
            "--data",
            json.dumps(data),
        ]

        log(f"Broadcasting: {message[:50]}...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(Path.home()),
        )

        output = result.stdout.strip() or result.stderr.strip()
        success = result.returncode == 0

        if success:
            log("Broadcast successful")
        else:
            log(f"Broadcast failed: {output[:100]}")

        return {
            "success": success,
            "output": output,
        }

    except subprocess.TimeoutExpired:
        log("Broadcast timeout")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        log(f"Broadcast error: {e}")
        return {"success": False, "error": str(e)}


def on_subagent_stop(hook_input: dict) -> dict:
    """Handle SubagentStop - release task claims and broadcast completion.

    On subagent stop:
    1. Load active task claims for this session
    2. Release each claim via claims_release
    3. Broadcast completion via hooks_notify
    4. Clear claims from state file
    """
    # Extract agent_id if available (for logging)
    agent_id = hook_input.get("agent_id", "unknown")
    session_id = get_session_id()

    log(f"SubagentStop received for agent: {agent_id}, session: {session_id}")

    # Load active claims
    claims_data = load_active_claims()
    active_claims = claims_data.get("claims", [])

    if not active_claims:
        log("No active task claims to release")
        return {}

    log(f"Found {len(active_claims)} active task claims to release")

    released_count = 0
    for claim in active_claims:
        issue_id = claim.get("issue_id")
        claimant = claim.get("claimant")
        description = claim.get("description", "unknown task")
        task_id = claim.get("task_id", "unknown")

        if not issue_id or not claimant:
            log(f"Skipping invalid claim: {claim}")
            continue

        # Release the claim
        release_result = call_claims_release(issue_id, claimant)

        if release_result.get("success"):
            released_count += 1

            # Broadcast completion
            notify_result = call_hooks_notify(
                message=f"Task completed: {description[:100]}",
                data={
                    "task_id": task_id,
                    "event": "completed",
                    "description": description,
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "completed_at": get_timestamp(),
                },
            )

            release_ok = release_result.get("success")
            notify_ok = notify_result.get("success")
            log(f"Released and broadcast task {task_id}: release={release_ok}, notify={notify_ok}")
        else:
            log(f"Failed to release task {task_id}: {release_result.get('error', 'unknown')}")

    # Clear all claims from state file
    save_active_claims({"claims": []})

    log(f"SubagentStop complete: released {released_count}/{len(active_claims)} claims")

    return {}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Task Release Hook - SubagentStop for releasing task claims")
    parser.add_argument(
        "--version",
        action="version",
        version="task_release.py 1.0.0",
    )
    # Parse args but we don't use them (for --help support)
    parser.parse_args()

    # Read hook input from stdin
    hook_input = {}
    if not sys.stdin.isatty():
        try:
            hook_input = json.load(sys.stdin)
        except json.JSONDecodeError:
            log("Invalid JSON input")

    try:
        result = on_subagent_stop(hook_input)
        print(json.dumps(result))
        return 0

    except Exception as e:
        log(f"Error in task_release: {e}")
        print(json.dumps({}))
        return 0  # Don't fail on errors


if __name__ == "__main__":
    sys.exit(main())
