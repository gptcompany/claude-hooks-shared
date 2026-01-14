#!/usr/bin/env python3
"""Repo Health Notification Hook.

Runs on session start to notify Claude of repo issues.
Only shows notification if there are significant issues.

Hook type: UserPromptSubmit (runs once at session start)
"""

import json
from pathlib import Path

# Only run once per session (check marker file)
MARKER_FILE = Path("/tmp/claude-repo-health-checked")
MAIN_REPOS = [
    Path("/media/sam/1TB/N8N_dev"),
    Path("/media/sam/1TB/UTXOracle"),
    Path("/media/sam/1TB/LiquidationHeatmap"),
    Path("/media/sam/1TB/nautilus_dev"),
]


def count_pycache(repo: Path) -> int:
    """Count __pycache__ directories."""
    try:
        return len(list(repo.rglob("__pycache__")))
    except Exception:
        return 0


def count_obsolete(repo: Path) -> int:
    """Count obsolete files."""
    count = 0
    for pattern in ["*.bak", "*.old", "*~", "*.orig"]:
        try:
            count += len(list(repo.rglob(pattern)))
        except Exception:
            pass
    return count


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

        pycache = count_pycache(repo)
        obsolete = count_obsolete(repo)

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
    if total_pycache > 200 or total_obsolete > 5:
        print(
            json.dumps(
                {
                    "hook": "repo-health-notify",
                    "status": "warning",
                    "message": f"Repo cleanup recommended: {total_pycache} __pycache__, {total_obsolete} obsolete files",
                    "details": repos_with_issues,
                    "action": "Run: python ~/.claude/scripts/repo-cleanup.py --all --clean",
                }
            )
        )


if __name__ == "__main__":
    main()
