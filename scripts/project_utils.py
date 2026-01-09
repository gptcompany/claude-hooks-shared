#!/usr/bin/env python3
"""
Shared utility functions for Claude Code hooks.

Provides automatic project name detection from:
1. Environment variable CLAUDE_PROJECT_NAME (override)
2. Git repository root directory name
3. Current working directory name (fallback)
"""

import os
import subprocess
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def get_project_name() -> str:
    """
    Auto-detect project name with fallback chain.

    Priority:
    1. CLAUDE_PROJECT_NAME env var (explicit override)
    2. Git repo root directory name
    3. Current working directory name

    Returns:
        Project name string (never empty, defaults to 'unknown')
    """
    # 1. Check environment variable first (allows override)
    if name := os.environ.get("CLAUDE_PROJECT_NAME"):
        return name

    # 2. Try to get from git repository root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=os.getcwd()
        )
        if result.returncode == 0:
            git_root = result.stdout.strip()
            if git_root:
                return Path(git_root).name
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # 3. Fallback to current directory name
    cwd = os.getcwd()
    if cwd and cwd != "/":
        return Path(cwd).name

    return "unknown"


def get_database_url() -> str:
    """
    Get database URL from environment with default.

    Returns:
        PostgreSQL connection URL
    """
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://n8n:n8n@localhost:5433/claude_sessions"
    )


def get_project_root() -> Path:
    """
    Get project root directory.

    Returns:
        Path to project root (git root or cwd)
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return Path.cwd()


if __name__ == "__main__":
    # Test auto-detection
    print(f"Project Name: {get_project_name()}")
    print(f"Project Root: {get_project_root()}")
    print(f"Database URL: {get_database_url()}")
