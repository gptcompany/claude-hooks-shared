#!/usr/bin/env python3
"""
PostToolUse Hook: Task Auto-Checkpoint

After Task tool (subagent) completes, automatically:
1. Log agent completion to stats
2. Create git checkpoint if there are changes

This replaces the non-functional SubagentStop hook type.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configuration
STATS_DIR = Path.cwd() / ".claude" / "stats"
COMPLETIONS_LOG = STATS_DIR / "subagent_completions.jsonl"
MIN_CHANGES_FOR_COMMIT = 5  # Minimum lines changed to trigger commit


def get_git_changes() -> dict:
    """Get git change statistics."""
    try:
        # Check for any changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        if not result.stdout.strip():
            return {"has_changes": False, "files": 0, "lines": 0}

        # Count changed files
        changed_files = len(result.stdout.strip().split("\n"))

        # Count changed lines
        diff_result = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        # Parse lines changed from diff --stat
        lines_changed = 0
        for line in diff_result.stdout.split("\n"):
            if "insertion" in line or "deletion" in line:
                # Extract numbers from "X files changed, Y insertions(+), Z deletions(-)"
                import re

                numbers = re.findall(r"(\d+) insertion|(\d+) deletion", line)
                for ins, dels in numbers:
                    lines_changed += int(ins) if ins else int(dels) if dels else 0

        return {
            "has_changes": True,
            "files": changed_files,
            "lines": lines_changed,
        }
    except Exception:
        return {"has_changes": False, "files": 0, "lines": 0}


def log_completion(agent_type: str, success: bool):
    """Log agent completion to stats file."""
    try:
        STATS_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_type,
            "success": success,
        }

        with open(COMPLETIONS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Silent fail


def create_checkpoint(agent_type: str, success: bool) -> bool:
    """Create git checkpoint after agent completion."""
    try:
        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            cwd=Path.cwd(),
        )

        # Create commit message
        status_emoji = "✅" if success else "⚠️"
        status_text = "SUCCESS" if success else "PARTIAL"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        commit_msg = f"""[{status_emoji} Agent: {agent_type}] {status_text}

Timestamp: {timestamp}

🤖 Generated with Claude Code (Auto-Checkpoint)
Co-Authored-By: Claude <noreply@anthropic.com>"""

        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        return result.returncode == 0
    except Exception:
        return False


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Only process Task tool
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Task":
        print(json.dumps({}))
        sys.exit(0)

    # Extract agent info from tool result
    tool_result = input_data.get("tool_result", {})

    # Try to determine agent type and success
    if isinstance(tool_result, dict):
        agent_type = tool_result.get("subagent_type", "unknown")
        # Infer success from result content
        result_text = str(tool_result).lower()
        success = "error" not in result_text and "failed" not in result_text
    elif isinstance(tool_result, str):
        agent_type = "unknown"
        success = "error" not in tool_result.lower()
    else:
        agent_type = "unknown"
        success = True

    # Log completion
    log_completion(agent_type, success)

    # Check if we should create checkpoint
    changes = get_git_changes()

    if not changes["has_changes"]:
        print(json.dumps({}))
        sys.exit(0)

    if changes["lines"] < MIN_CHANGES_FOR_COMMIT:
        # Not enough changes for checkpoint
        print(json.dumps({}))
        sys.exit(0)

    # Create checkpoint
    checkpoint_created = create_checkpoint(agent_type, success)

    if checkpoint_created:
        response = {
            "notification": f"📸 Auto-checkpoint: {agent_type} ({changes['files']} files, {changes['lines']} lines)",
        }
    else:
        response = {}

    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
