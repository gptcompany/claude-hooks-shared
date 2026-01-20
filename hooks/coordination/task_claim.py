#!/usr/bin/env python3
"""Task Claim Hook - PreToolUse hook for Task tool.

Claims a task when a subagent is spawned for visibility into active work.
Task claims are INFORMATIONAL only - they don't block, just provide visibility.

Hook type: PreToolUse (matcher: Task)

Usage:
  echo '{"tool_input": {"description": "Implement feature X"}}' | task_claim.py

Output: JSON {} (always allows task to proceed)
"""

import argparse
import hashlib
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

# Session state file for tracking active task claims
TASK_CLAIMS_FILE = LOG_DIR / "active_task_claims.json"


def get_timestamp() -> str:
    """Get ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


def log(msg: str):
    """Log message to coordination log file."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{get_timestamp()} [task_claim] {msg}\n")
    except Exception:
        pass


def get_session_id() -> str:
    """Get or generate session ID.

    Uses environment variable if set, otherwise generates one
    and stores in session state file.
    """
    if session_id := os.environ.get("CLAUDE_SESSION_ID"):
        return session_id

    session_file = LOG_DIR / "session_id"
    if session_file.exists():
        try:
            return session_file.read_text().strip()
        except Exception:
            pass

    # Generate new session ID
    import uuid

    session_id = f"session-{uuid.uuid4().hex[:8]}"
    try:
        session_file.write_text(session_id)
    except Exception:
        pass

    return session_id


def generate_task_id(description: str) -> str:
    """Generate unique task ID from description hash + timestamp component."""
    # Use hash of description for consistency + timestamp for uniqueness
    desc_hash = hashlib.sha256(description.encode()).hexdigest()[:8]
    time_component = datetime.now(timezone.utc).strftime("%H%M%S")
    return f"task-{desc_hash}-{time_component}"


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


def call_claims_claim(issue_id: str, claimant: str, context: str) -> dict:
    """Call claude-flow claims_claim via CLI.

    Returns dict with success status and claim info.
    """
    try:
        cmd = [
            "npx",
            "-y",
            "claude-flow@latest",
            "claims",
            "claim",
            "--issue-id",
            issue_id,
            "--claimant",
            claimant,
            "--context",
            context,
        ]

        log(f"Calling: {' '.join(cmd[:6])}...")

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
            log(f"Claim successful for {issue_id}")
        else:
            log(f"Claim failed for {issue_id}: {output[:100]}")

        return {
            "success": success,
            "output": output,
        }

    except subprocess.TimeoutExpired:
        log(f"Claim timeout for {issue_id}")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        log(f"Claim error for {issue_id}: {e}")
        return {"success": False, "error": str(e)}


def on_pre_task(hook_input: dict) -> dict:
    """Handle PreToolUse Task - claim task for visibility.

    Task claims are INFORMATIONAL only. They don't block the task
    from proceeding - they just provide visibility into what's running.
    """
    tool_input = hook_input.get("tool_input", {})

    # Extract task description from description or prompt field
    description = (
        tool_input.get("description") or tool_input.get("prompt") or "unknown task"
    )
    description = str(description)[:200]  # Truncate to 200 chars

    # Generate task ID and session ID
    task_id = generate_task_id(description)
    session_id = get_session_id()

    # Build claim identifiers
    issue_id = f"task:{task_id}"
    claimant = f"agent:{session_id}:task"
    context = description

    log(f"Claiming task: {task_id} - {description[:50]}...")

    # Call claude-flow claims_claim
    result = call_claims_claim(issue_id, claimant, context)

    # Store in session state for later release (regardless of claim success)
    claims = load_active_claims()
    claims["claims"].append(
        {
            "task_id": task_id,
            "issue_id": issue_id,
            "claimant": claimant,
            "description": description,
            "claimed_at": get_timestamp(),
            "claim_success": result.get("success", False),
        }
    )
    save_active_claims(claims)

    log(
        f"Task claim registered: {task_id} (claim_api_success={result.get('success', False)})"
    )

    # INFORMATIONAL: Always allow task to proceed
    return {}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Task Claim Hook - PreToolUse for Task tool"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="task_claim.py 1.0.0",
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
        result = on_pre_task(hook_input)
        print(json.dumps(result))
        return 0

    except Exception as e:
        log(f"Error in task_claim: {e}")
        print(json.dumps({}))
        return 0  # Don't block on errors


if __name__ == "__main__":
    sys.exit(main())
