#!/usr/bin/env python3
"""
Stop Hook: Auto-activate Ralph Loop after significant code changes.

Triggers Ralph Loop when Claude stops after:
1. Significant code changes (>20 lines modified)
2. Multiple code files changed (2+)

Based on auto-alpha-debug.py but activates Ralph instead of spawning agent.
Ralph provides unified loop with circuit breakers and exit criteria.

DUAL-SOURCE DETECTION:
- Primary: Uncommitted changes (git diff HEAD)
- Fallback: Last commit if recent (< MAX_COMMIT_AGE_MINUTES)
"""

import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Configuration
MIN_LINES_CHANGED = 20  # Minimum lines to trigger
MAX_COMMIT_AGE_MINUTES = 5  # Only analyze commits within this window
ANALYZED_COMMITS_FILE = "analyzed_commits.json"
COOLDOWN_MINUTES = 10  # Minimum time between triggers
COOLDOWN_FILE = "ralph_cooldown.json"

# Ralph state file location
RALPH_STATE = Path.home() / ".claude" / "ralph" / "state.json"

# Files/patterns to EXCLUDE from triggering
EXCLUDE_PATTERNS = [
    ".claude/",
    ".git/",
    ".github/",
    ".vscode/",
    "node_modules/",
    "target/",
    "__pycache__/",
    "*.md",
    "*.json",
    "*.yml",
    "*.yaml",
    "*.toml",
    "*.lock",
    "*.txt",
    "*.log",
    "*.csv",
    "*.html",
    "*.css",
    "CLAUDE.md",
    "README.md",
    "LICENSE",
    "Makefile",
    "Dockerfile",
]

# Code file extensions that SHOULD trigger
CODE_EXTENSIONS = [
    ".py",
    ".rs",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cc",
    ".cxx",
    ".java",
    ".kt",
    ".kts",
    ".rb",
    ".php",
    ".swift",
    ".scala",
    ".sh",
    ".bash",
    ".sql",
]

# Code directories (boost priority)
CODE_DIRECTORIES = [
    "src/",
    "lib/",
    "scripts/",
    "tests/",
    "test/",
    "api/",
    "backend/",
    "frontend/",
    "core/",
    "pkg/",
    "cmd/",
    "internal/",
    "strategies/",
]


def should_exclude_file(filepath: str) -> bool:
    """Check if file should be excluded from triggering."""
    filepath_lower = filepath.lower()

    for pattern in EXCLUDE_PATTERNS:
        if pattern.endswith("/"):
            dir_name = pattern.rstrip("/")
            if f"/{dir_name}/" in f"/{filepath_lower}/" or filepath_lower.startswith(
                f"{dir_name}/"
            ):
                return True
        elif fnmatch.fnmatch(filepath_lower, pattern.lower()):
            return True
    return False


def is_code_file(filepath: str) -> bool:
    """Check if file is actual code that should trigger."""
    filepath_lower = filepath.lower()

    for ext in CODE_EXTENSIONS:
        if filepath_lower.endswith(ext):
            return True

    for code_dir in CODE_DIRECTORIES:
        dir_name = code_dir.rstrip("/")
        if f"/{dir_name}/" in f"/{filepath_lower}/" or filepath_lower.startswith(f"{dir_name}/"):
            return True

    return False


def _empty_changes(source: str = "unknown") -> dict:
    """Return empty changes dict."""
    return {
        "files_changed": 0,
        "lines_added": 0,
        "lines_deleted": 0,
        "total_lines": 0,
        "code_files": [],
        "source": source,
    }


def get_git_changes() -> dict:
    """Analyze uncommitted changes, filtering out config files."""
    try:
        result_files = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            errors="replace",
        )
        result_staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            timeout=5,
            errors="replace",
        )

        if result_files.returncode != 0 and result_staged.returncode != 0:
            return _empty_changes("uncommitted")

        all_files = set(
            result_files.stdout.strip().split("\n") + result_staged.stdout.strip().split("\n")
        )
        all_files.discard("")

        code_files = [f for f in all_files if is_code_file(f) and not should_exclude_file(f)]

        if not code_files:
            return _empty_changes("uncommitted")

        # Get line counts
        result = subprocess.run(
            ["git", "diff", "--numstat", "--cached", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            errors="replace",
        )
        result2 = subprocess.run(
            ["git", "diff", "--numstat"],
            capture_output=True,
            text=True,
            timeout=5,
            errors="replace",
        )

        output = result.stdout + result2.stdout
        lines_added, lines_deleted, files_changed = 0, 0, 0
        seen_files = set()

        for line in output.strip().split("\n"):
            if not line or "\t" not in line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                added_str, deleted_str, filename = parts[0], parts[1], parts[2]

                if "=>" in filename:
                    filename = re.sub(r"\{[^}]* => ([^}]*)\}", r"\1", filename)
                    if "=>" in filename:
                        filename = filename.split("=>")[-1].strip()

                if filename in seen_files:
                    continue
                seen_files.add(filename)

                if is_code_file(filename) and not should_exclude_file(filename):
                    files_changed += 1
                    if added_str.isdigit():
                        lines_added += int(added_str)
                    if deleted_str.isdigit():
                        lines_deleted += int(deleted_str)

        return {
            "files_changed": files_changed,
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
            "total_lines": lines_added + lines_deleted,
            "code_files": code_files,
            "source": "uncommitted",
        }
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        print(f"Warning: git analysis failed: {e}", file=sys.stderr)
        return _empty_changes("uncommitted")


def get_last_commit_changes() -> dict:
    """Analyze the last commit if it's recent enough."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct %H"],
            capture_output=True,
            text=True,
            timeout=5,
            errors="replace",
        )

        if result.returncode != 0 or not result.stdout.strip():
            return _empty_changes("last_commit")

        parts = result.stdout.strip().split(" ", 1)
        if len(parts) != 2:
            return _empty_changes("last_commit")

        commit_time = int(parts[0])
        commit_hash = parts[1]

        age_minutes = (time.time() - commit_time) / 60
        if age_minutes > MAX_COMMIT_AGE_MINUTES:
            return _empty_changes("last_commit")

        # Check if already analyzed
        project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
        tracking_file = project_dir / ".claude" / "stats" / ANALYZED_COMMITS_FILE
        if tracking_file.exists():
            try:
                data = json.loads(tracking_file.read_text())
                if commit_hash in data.get("commits", []):
                    return _empty_changes("last_commit")
            except (OSError, json.JSONDecodeError):
                pass

        # Get files changed
        result_files = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1..HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            errors="replace",
        )

        if result_files.returncode != 0:
            return _empty_changes("last_commit")

        all_files = set(result_files.stdout.strip().split("\n"))
        all_files.discard("")
        code_files = [f for f in all_files if is_code_file(f) and not should_exclude_file(f)]

        if not code_files:
            return _empty_changes("last_commit")

        result_stats = subprocess.run(
            ["git", "diff", "--numstat", "HEAD~1..HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            errors="replace",
        )

        lines_added, lines_deleted, files_changed = 0, 0, 0
        for line in result_stats.stdout.strip().split("\n"):
            if not line or "\t" not in line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                added_str, deleted_str, filename = parts[0], parts[1], parts[2]
                if "=>" in filename:
                    filename = re.sub(r"\{[^}]* => ([^}]*)\}", r"\1", filename)
                    if "=>" in filename:
                        filename = filename.split("=>")[-1].strip()

                if is_code_file(filename) and not should_exclude_file(filename):
                    files_changed += 1
                    if added_str.isdigit():
                        lines_added += int(added_str)
                    if deleted_str.isdigit():
                        lines_deleted += int(deleted_str)

        return {
            "files_changed": files_changed,
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
            "total_lines": lines_added + lines_deleted,
            "code_files": code_files,
            "source": "last_commit",
            "commit_hash": commit_hash,
            "commit_age_minutes": round(age_minutes, 1),
        }
    except Exception as e:
        print(f"Warning: last commit analysis failed: {e}", file=sys.stderr)
        return _empty_changes("last_commit")


def is_ralph_already_active() -> bool:
    """Check if Ralph is already active."""
    if RALPH_STATE.exists():
        try:
            state = json.loads(RALPH_STATE.read_text())
            return state.get("active", False)
        except (json.JSONDecodeError, OSError):
            pass
    return False


def is_in_cooldown() -> tuple[bool, float]:
    """Check if we're still in cooldown period."""
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    cooldown_file = project_dir / ".claude" / "stats" / COOLDOWN_FILE

    try:
        if not cooldown_file.exists():
            return False, 0

        data = json.loads(cooldown_file.read_text())
        last_trigger = data.get("last_trigger_time", 0)
        elapsed_minutes = (time.time() - last_trigger) / 60
        remaining = COOLDOWN_MINUTES - elapsed_minutes

        if remaining > 0:
            return True, remaining
        return False, 0
    except (OSError, json.JSONDecodeError, ValueError):
        return False, 0


def update_cooldown() -> None:
    """Update cooldown timestamp after triggering."""
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    cooldown_file = project_dir / ".claude" / "stats" / COOLDOWN_FILE

    try:
        cooldown_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_trigger_time": time.time(),
            "last_trigger_iso": datetime.now().isoformat(),
        }
        cooldown_file.write_text(json.dumps(data, indent=2))
    except (OSError, PermissionError) as e:
        print(f"Warning: Could not update cooldown: {e}", file=sys.stderr)


def activate_ralph(changes: dict, trigger_reason: str) -> dict:
    """Activate Ralph Loop mode."""
    RALPH_STATE.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "active": True,
        "original_prompt": f"[AUTO-TRIGGERED] Verify code changes: {trigger_reason}",
        "iteration": 0,
        "started_at": datetime.now().isoformat(),
        "trigger_source": "auto-ralph",
        "changes": {
            "files": changes["files_changed"],
            "lines": changes["total_lines"],
            "code_files": changes.get("code_files", [])[:5],
        },
    }

    RALPH_STATE.write_text(json.dumps(state, indent=2))
    return state


def should_trigger(changes: dict) -> tuple[bool, str]:
    """Decide if Ralph should be activated."""
    code_files = changes.get("code_files", [])

    if not code_files:
        return False, "No code files changed"

    if changes["total_lines"] < MIN_LINES_CHANGED:
        return False, f"Only {changes['total_lines']} lines (min: {MIN_LINES_CHANGED})"

    # Trigger conditions
    if changes["total_lines"] >= 50:
        return (
            True,
            f"Significant changes: {changes['total_lines']} lines in {len(code_files)} files",
        )

    if len(code_files) >= 2:
        return True, f"Multiple code files: {len(code_files)}"

    if changes["total_lines"] >= MIN_LINES_CHANGED:
        return True, f"Code changes: {changes['total_lines']} lines in {code_files[0]}"

    return False, "No trigger conditions met"


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Kill switch check
    kill_switches = [
        Path.cwd() / ".claude" / "SKIP_AUTO_RALPH",
        Path.cwd() / "SKIP_AUTO_RALPH",
    ]
    for ks in kill_switches:
        if ks.exists():
            print(json.dumps({}))
            sys.exit(0)

    # Skip if Ralph already active
    if is_ralph_already_active():
        print(json.dumps({}))
        sys.exit(0)

    # Cooldown check
    in_cooldown, remaining = is_in_cooldown()
    if in_cooldown:
        print(f"Auto-Ralph in cooldown ({remaining:.1f} min remaining)", file=sys.stderr)
        print(json.dumps({}))
        sys.exit(0)

    # Analyze changes - primary: uncommitted
    changes = get_git_changes()
    trigger, reason = should_trigger(changes)

    # Fallback: last commit
    if not trigger:
        changes = get_last_commit_changes()
        trigger, reason = should_trigger(changes)
        if trigger:
            reason = f"[LAST COMMIT] {reason}"

    if not trigger:
        print(json.dumps({}))
        sys.exit(0)

    # Activate Ralph
    activate_ralph(changes, reason)
    update_cooldown()

    # Build response
    source_info = changes.get("source", "unknown")
    if source_info == "last_commit":
        commit_hash = changes.get("commit_hash", "")[:8]
        source_info = f"last commit ({commit_hash})"

    response = {
        "continueWithPrompt": f"""
## Ralph Loop Auto-Activated

**Reason**: {reason}
**Source**: {source_info}

Changes detected:
- Files: {changes["files_changed"]}
- Lines: {changes["total_lines"]} (+{changes["lines_added"]}/-{changes["lines_deleted"]})

### Exit Criteria (ALL must pass)
- All tests pass: `uv run pytest tests/ -x`
- No lint errors: `uv run ruff check .`

### Circuit Breakers
- Max 15 iterations | Stop on 3 consecutive errors | Stop on 5 no-progress

Run tests and fix any issues found. Type "STOP RALPH" to exit early.
""",
    }

    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
