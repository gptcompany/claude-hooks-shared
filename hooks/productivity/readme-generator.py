#!/usr/bin/env python3
"""
PostToolUse Hook: README Auto-Generation on Git Commit

Triggers after successful git commit to:
1. Validate README.md consistency with current codebase
2. Auto-update README.md if significant changes detected
3. Auto-create README.md if missing

Hook Type: PostToolUse
Matcher: Bash
Timeout: 10s
"""

import json
import re
import subprocess
import sys
from pathlib import Path

# Configuration
README_LOCATIONS = [
    "README.md",
    "docs/README.md",
]

# Files that indicate README-relevant changes
README_TRIGGER_PATTERNS = [
    r"^src/",
    r"^lib/",
    r"^api/",
    r"^app/",
    r"^scripts/",
    r"pyproject\.toml$",
    r"Cargo\.toml$",
    r"package\.json$",
    r"requirements\.txt$",
    r"setup\.py$",
    r"Dockerfile$",
    r"docker-compose",
    r"\.env\.example$",
    r"Makefile$",
    r"CLAUDE\.md$",
    r"ARCHITECTURE\.md$",
]

# Files to exclude from triggering
EXCLUDE_PATTERNS = [
    r"^\.claude/",
    r"^\.git/",
    r"__pycache__",
    r"\.pyc$",
    r"^tests/",
    r"^test_",
    r"\.lock$",
    r"node_modules/",
]

# Minimum commit count between README checks (to avoid over-triggering)
MIN_COMMITS_BETWEEN_CHECKS = 5


def is_git_commit_command(command: str) -> bool:
    """Check if command is a git commit."""
    return bool(re.search(r"\bgit\s+commit\b", command))


def is_successful_commit(output: str) -> bool:
    """Check if commit output indicates success."""
    return bool(re.search(r"\[\w+[-\w]*\s+[a-f0-9]+\]", output))


def get_last_commit_files() -> list[str]:
    """Get files changed in the last commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1..HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass
    return []


def get_commit_count_since_readme_change() -> int:
    """Get number of commits since README.md was last modified."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "README.md"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Get commit count since last README change
            readme_commit = result.stdout.strip().split("\n")[0].split()[0]
            count_result = subprocess.run(
                ["git", "rev-list", "--count", f"{readme_commit}..HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if count_result.returncode == 0:
                return int(count_result.stdout.strip())
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError):
        pass
    return 0


def should_exclude_file(file: str) -> bool:
    """Check if file should be excluded from triggering."""
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, file):
            return True
    return False


def is_readme_relevant(file: str) -> bool:
    """Check if file is README-relevant."""
    if should_exclude_file(file):
        return False
    for pattern in README_TRIGGER_PATTERNS:
        if re.search(pattern, file):
            return True
    return False


def has_readme_relevant_changes(files: list[str]) -> bool:
    """Check if any changed files are README-relevant."""
    return any(is_readme_relevant(f) for f in files)


def find_readme_file(project_dir: Path) -> Path | None:
    """Find existing README.md in known locations."""
    for loc in README_LOCATIONS:
        readme_file = project_dir / loc
        if readme_file.exists():
            return readme_file
    return None


def get_project_name(project_dir: Path) -> str:
    """Get project name from directory or git remote."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_dir,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            match = re.search(r"/([^/]+?)(?:\.git)?$", url)
            if match:
                return match.group(1)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass
    return project_dir.name


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Get tool info
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_output = input_data.get("tool_output", {})

    # Only process Bash tool
    if tool_name != "Bash":
        sys.exit(0)

    command = tool_input.get("command", "")
    stdout = tool_output.get("stdout", "")
    stderr = tool_output.get("stderr", "")
    output = stdout + stderr

    # Check if this is a successful git commit
    if not is_git_commit_command(command):
        sys.exit(0)

    if not is_successful_commit(output):
        sys.exit(0)

    # Get changed files
    changed_files = get_last_commit_files()

    if not changed_files:
        sys.exit(0)

    # Check if changes are README-relevant
    relevant_files = [f for f in changed_files if is_readme_relevant(f)]

    if not relevant_files:
        sys.exit(0)

    # Check commit count to avoid over-triggering
    project_dir = Path.cwd()
    readme_file = find_readme_file(project_dir)

    if readme_file:
        commits_since = get_commit_count_since_readme_change()
        if commits_since < MIN_COMMITS_BETWEEN_CHECKS:
            # README was recently updated, skip this check
            sys.exit(0)

    project_name = get_project_name(project_dir)

    # Prepare validation context
    if readme_file:
        mode = "VALIDATE"
        readme_path = str(readme_file)
    else:
        mode = "CREATE"
        readme_path = str(project_dir / "README.md")

    # Build file list for display (max 10)
    file_list = "\n".join(f"  - {f}" for f in relevant_files[:10])
    if len(relevant_files) > 10:
        file_list += f"\n  ... and {len(relevant_files) - 10} more"

    # Trigger readme-generator agent
    response = {
        "continue": True,
        "systemMessage": f"""
══════════════════════════════════════════════════════════════
           README VALIDATION TRIGGERED
══════════════════════════════════════════════════════════════
Project: {project_name}
Mode: {mode}
README file: {readme_path}
Files changed: {len(relevant_files)}

Changed files (README-relevant):
{file_list}

══════════════════════════════════════════════════════════════

INSTRUCTION: Use the Task tool to spawn the **readme-generator**
subagent with subagent_type='general-purpose'.

Provide this prompt to the agent:

---
Generate or validate README.md for project: {project_name}
Mode: {mode}
README path: {readme_path}
Recent changes: {", ".join(relevant_files[:5])}

Tasks:
1. {"Read existing README.md at " + readme_path if mode == "VALIDATE" else "Analyze codebase structure"}
2. Check CLAUDE.md and ARCHITECTURE.md for project context
3. Verify README sections are current and accurate:
   - Project description
   - Quick start / Installation
   - Usage examples
   - Configuration
   - Development setup
4. Update outdated sections or create missing README
5. Ensure examples and paths are correct
6. Report changes made

Output: Brief report of README status and any updates made.
---

Start the readme-generator task now.
""",
    }

    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
