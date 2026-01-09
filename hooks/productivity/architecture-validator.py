#!/usr/bin/env python3
"""
PostToolUse Hook: Architecture Validation on Git Commit

Triggers after successful git commit to:
1. Validate implementation consistency with ARCHITECTURE.md
2. Auto-update ARCHITECTURE.md if new patterns detected
3. Auto-create ARCHITECTURE.md if missing

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
ARCHITECTURE_LOCATIONS = [
    "docs/ARCHITECTURE.md",
    "ARCHITECTURE.md",
    "architecture/ARCHITECTURE.md",
]

# Files that indicate architecture-relevant changes
ARCHITECTURE_TRIGGER_PATTERNS = [
    r"^src/",
    r"^lib/",
    r"^api/",
    r"^app/",
    r"^scripts/",
    r"^strategies/",
    r"^monitoring/",
    r"^feeds/",
    r"\.py$",
    r"\.rs$",
    r"\.ts$",
    r"\.tsx$",
    r"Dockerfile",
    r"docker-compose",
    r"\.sql$",
    r"pyproject\.toml$",
    r"Cargo\.toml$",
]

# Files to exclude from triggering
EXCLUDE_PATTERNS = [
    r"\.md$",
    r"\.json$",
    r"\.txt$",
    r"^\.claude/",
    r"^\.git/",
    r"__pycache__",
    r"\.pyc$",
    r"^tests/",
    r"^test_",
]


def is_git_commit_command(command: str) -> bool:
    """Check if command is a git commit."""
    return bool(re.search(r"\bgit\s+commit\b", command))


def is_successful_commit(output: str) -> bool:
    """Check if commit output indicates success."""
    # Successful commit patterns:
    # - "[branch abc1234] Commit message"
    # - "1 file changed, X insertions"
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


def should_exclude_file(file: str) -> bool:
    """Check if file should be excluded from triggering."""
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, file):
            return True
    return False


def is_architecture_relevant(file: str) -> bool:
    """Check if file is architecture-relevant."""
    if should_exclude_file(file):
        return False
    for pattern in ARCHITECTURE_TRIGGER_PATTERNS:
        if re.search(pattern, file):
            return True
    return False


def has_architecture_relevant_changes(files: list[str]) -> bool:
    """Check if any changed files are architecture-relevant."""
    return any(is_architecture_relevant(f) for f in files)


def find_architecture_file(project_dir: Path) -> Path | None:
    """Find existing ARCHITECTURE.md in known locations."""
    for loc in ARCHITECTURE_LOCATIONS:
        arch_file = project_dir / loc
        if arch_file.exists():
            return arch_file
    return None


def get_project_name(project_dir: Path) -> str:
    """Get project name from directory or git remote."""
    # Try git remote
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
            # Extract repo name from URL
            match = re.search(r"/([^/]+?)(?:\.git)?$", url)
            if match:
                return match.group(1)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass

    # Fallback to directory name
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

    # Check if changes are architecture-relevant
    relevant_files = [f for f in changed_files if is_architecture_relevant(f)]

    if not relevant_files:
        sys.exit(0)

    # Find or note missing ARCHITECTURE.md
    project_dir = Path.cwd()
    arch_file = find_architecture_file(project_dir)
    project_name = get_project_name(project_dir)

    # Prepare validation context
    if arch_file:
        mode = "VALIDATE"
        arch_path = str(arch_file)
    else:
        mode = "CREATE"
        arch_path = str(project_dir / "docs" / "ARCHITECTURE.md")

    # Build file list for display (max 15)
    file_list = "\n".join(f"  - {f}" for f in relevant_files[:15])
    if len(relevant_files) > 15:
        file_list += f"\n  ... and {len(relevant_files) - 15} more"

    # Trigger architecture-validator agent
    response = {
        "continue": True,
        "systemMessage": f"""
══════════════════════════════════════════════════════════════
         ARCHITECTURE VALIDATION TRIGGERED
══════════════════════════════════════════════════════════════
Project: {project_name}
Mode: {mode}
Architecture file: {arch_path}
Files changed: {len(relevant_files)}

Changed files (architecture-relevant):
{file_list}

══════════════════════════════════════════════════════════════

INSTRUCTION: Use the Task tool to spawn the **architecture-validator**
subagent with subagent_type='architecture-validator'.

The agent will:
1. {"Read and parse existing " + arch_path if mode == "VALIDATE" else "Analyze codebase to generate ARCHITECTURE.md"}
2. Analyze commit changes for architectural impact
3. {"Update ARCHITECTURE.md if new patterns/components detected" if mode == "VALIDATE" else "Create comprehensive ARCHITECTURE.md with ASCII diagrams"}
4. Produce validation report (PASS/WARN/FAIL)

Provide this context to the agent:
- Mode: {mode}
- Architecture path: {arch_path}
- Changed files: {", ".join(relevant_files[:10])}

Start architecture-validator agent now.
""",
    }

    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
