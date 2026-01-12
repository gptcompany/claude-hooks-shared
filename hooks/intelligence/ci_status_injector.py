#!/usr/bin/env python3
"""
CI Status Injector - UserPromptSubmit Hook (PostgreSQL Version)

Reads CI status from PostgreSQL and injects into Claude context.
Only injects status for the current repository.

Table: ci_status (in n8n database)
Written by: N8N GitHub CI Status Notifier workflow

Security: Uses parameterized queries to prevent SQL injection.
"""

import json
import os
import re
import subprocess
import sys

# PostgreSQL connection - credentials from environment only (no defaults)
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5433")
PG_USER = os.getenv("PG_USER")
PG_PASS = os.getenv("PG_PASS")
PG_DB = os.getenv("PG_DB", "n8n")

MAX_AGE_HOURS = 24  # Ignore status older than this

# Regex for valid GitHub repo format: owner/repo
VALID_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")


def sanitize_repo(repo: str) -> str | None:
    """Sanitize and validate repository name to prevent SQL injection."""
    if not repo:
        return None

    # Strip whitespace
    repo = repo.strip()

    # Validate format: must be owner/repo with safe characters only
    if not VALID_REPO_PATTERN.match(repo):
        return None

    # Additional safety: max length
    if len(repo) > 200:
        return None

    return repo


def get_current_repo() -> str | None:
    """Get current repository from git remote."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Extract owner/repo from various URL formats
            # https://github.com/owner/repo.git
            # git@github.com:owner/repo.git
            if "github.com" in url:
                if url.startswith("git@"):
                    # git@github.com:owner/repo.git
                    repo = url.split(":")[-1].replace(".git", "")
                else:
                    # https://github.com/owner/repo.git
                    parts = url.split("github.com/")[-1].replace(".git", "")
                    repo = parts
                return sanitize_repo(repo)
    except Exception:
        pass
    return None


def query_ci_status(repo: str) -> list[dict]:
    """Query pending CI status for repo from PostgreSQL using parameterized query."""
    # Credentials check
    if not PG_USER or not PG_PASS:
        return []

    # Repo already sanitized, but double-check
    safe_repo = sanitize_repo(repo)
    if not safe_repo:
        return []

    try:
        # Use psql with -v to pass variable safely (prevents SQL injection)
        # The variable is then referenced as :'varname' in the query
        query = """
        SELECT json_agg(row_to_json(t))
        FROM (
            SELECT id, repo, repo_name, branch, pr_number, conclusion,
                   run_url, message, pending_action, created_at
            FROM ci_status
            WHERE repo = :'repo_param'
              AND injected = FALSE
              AND created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 5
        ) t;
        """

        result = subprocess.run(
            [
                "psql",
                "-h",
                PG_HOST,
                "-p",
                PG_PORT,
                "-U",
                PG_USER,
                "-d",
                PG_DB,
                "-v",
                f"repo_param={safe_repo}",  # Safe parameter passing
                "-t",  # Tuples only
                "-A",  # Unaligned
                "-c",
                query,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "PGPASSWORD": PG_PASS},
        )

        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            return data if data else []
    except Exception:
        pass
    return []


def mark_as_injected(ids: list[int]) -> None:
    """Mark CI status records as injected using safe integer list."""
    if not ids:
        return

    # Credentials check
    if not PG_USER or not PG_PASS:
        return

    # Validate all IDs are positive integers (prevents injection)
    try:
        safe_ids = [int(i) for i in ids if isinstance(i, (int, float)) and i > 0]
        if not safe_ids:
            return
    except (ValueError, TypeError):
        return

    try:
        # Safe: ids_str contains only validated integers
        ids_str = ",".join(str(i) for i in safe_ids)
        query = f"UPDATE ci_status SET injected = TRUE WHERE id IN ({ids_str});"

        subprocess.run(
            [
                "psql",
                "-h",
                PG_HOST,
                "-p",
                PG_PORT,
                "-U",
                PG_USER,
                "-d",
                PG_DB,
                "-c",
                query,
            ],
            capture_output=True,
            timeout=10,
            env={**os.environ, "PGPASSWORD": PG_PASS},
        )
    except Exception:
        pass


def format_status(statuses: list[dict]) -> str:
    """Format CI statuses for injection."""
    parts = []

    for s in statuses:
        conclusion = s.get("conclusion", "unknown")
        pr_number = s.get("pr_number")
        repo_name = s.get("repo_name", "repo")
        pending_action = s.get("pending_action")

        emoji = "✅" if conclusion == "success" else "❌" if conclusion == "failure" else "⚠️"

        status_parts = [f"{emoji} CI"]
        if pr_number:
            status_parts.append(f"#{pr_number}")
        status_parts.append(f"on {repo_name}")

        if pending_action == "merge":
            status_parts.append("- ready to merge!")
        elif pending_action == "fix":
            status_parts.append("- needs fix")

        parts.append(" ".join(status_parts))

    return " | ".join(parts)


def main():
    try:
        _input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    # Get current repo (already sanitized)
    current_repo = get_current_repo()
    if not current_repo:
        print(json.dumps({}))
        sys.exit(0)

    # Query pending CI statuses for this repo
    statuses = query_ci_status(current_repo)
    if not statuses:
        print(json.dumps({}))
        sys.exit(0)

    # Format and output
    formatted = format_status(statuses)
    output = {"additionalContext": f"[{formatted}]"}
    print(json.dumps(output))

    # Mark as injected (one-time)
    ids = [s["id"] for s in statuses if s.get("id")]
    mark_as_injected(ids)

    sys.exit(0)


if __name__ == "__main__":
    main()
