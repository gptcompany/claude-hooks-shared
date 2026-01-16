#!/usr/bin/env python3
"""Repo Health Notification Hook.

Runs on session start to notify Claude of repo issues.
Only shows notification if there are significant issues.

Hook type: UserPromptSubmit (runs once at session start)
"""

import json
import os
from pathlib import Path

# Only run once per session (check marker file)
MARKER_FILE = Path("/tmp/claude-repo-health-checked")

# Config from environment or defaults
PYCACHE_THRESHOLD = int(os.environ.get("REPO_HEALTH_PYCACHE_THRESHOLD", 100))
OBSOLETE_THRESHOLD = int(os.environ.get("REPO_HEALTH_OBSOLETE_THRESHOLD", 2))

MAIN_REPOS = [
    Path("/media/sam/1TB/N8N_dev"),
    Path("/media/sam/1TB/UTXOracle"),
    Path("/media/sam/1TB/LiquidationHeatmap"),
    Path("/media/sam/1TB/nautilus_dev"),
]

# Skip these directories for speed
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "data", ".worktrees"}


def count_pycache_fast(repo: Path) -> int:
    """Count __pycache__ directories (fast, skips heavy dirs)."""
    count = 0
    try:
        for _root, dirs, _ in os.walk(repo):
            # Skip heavy directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            if "__pycache__" in dirs:
                count += 1
                dirs.remove("__pycache__")  # Don't recurse into it
    except Exception:
        pass
    return count


def count_obsolete_fast(repo: Path) -> int:
    """Count obsolete files (fast, top-level only + .claude/)."""
    count = 0
    patterns = [".bak", ".old", ".orig", "~"]

    # Check top-level
    try:
        for f in repo.iterdir():
            if f.is_file() and any(f.name.endswith(p) for p in patterns):
                count += 1
    except Exception:
        pass

    # Check .claude/ specifically
    claude_dir = repo / ".claude"
    if claude_dir.exists():
        try:
            for f in claude_dir.rglob("*"):
                if f.is_file() and any(f.name.endswith(p) for p in patterns):
                    count += 1
        except Exception:
            pass

    return count


def get_worst_repo(repos_with_issues: list) -> str:
    """Get the repo with most issues for prioritized action."""
    if not repos_with_issues:
        return ""
    worst = max(repos_with_issues, key=lambda x: x["pycache"] + x["obsolete"] * 10)
    return worst["name"]


def main():
    # Skip if already checked this session
    if MARKER_FILE.exists():
        return

    # Create marker
    MARKER_FILE.touch()

    # Quick health check
    total_pycache = 0
    total_obsolete = 0
    repos_with_issues = []

    for repo in MAIN_REPOS:
        if not repo.exists():
            continue

        pycache = count_pycache_fast(repo)
        obsolete = count_obsolete_fast(repo)

        total_pycache += pycache
        total_obsolete += obsolete

        if pycache > 50 or obsolete > 0:
            repos_with_issues.append(
                {
                    "name": repo.name,
                    "pycache": pycache,
                    "obsolete": obsolete,
                }
            )

    # Only notify if significant issues
    if total_pycache > PYCACHE_THRESHOLD or total_obsolete > OBSOLETE_THRESHOLD:
        worst = get_worst_repo(repos_with_issues)

        # Prioritized action suggestion
        if total_obsolete > 0:
            action = f"python ~/.claude/scripts/repo-cleanup.py /media/sam/1TB/{worst} --clean --force"
            priority = "obsolete files first"
        else:
            action = "python ~/.claude/scripts/repo-cleanup.py --all --clean --force"
            priority = "__pycache__ cleanup"

        print(
            json.dumps(
                {
                    "hook": "repo-health-notify",
                    "status": "warning",
                    "message": f"Cleanup: {total_pycache} __pycache__, {total_obsolete} obsolete",
                    "priority": priority,
                    "worst_repo": worst,
                    "action": action,
                }
            )
        )


if __name__ == "__main__":
    main()
