#!/usr/bin/env python3
"""
PreToolUse Hook: TDD Guard Check

Checks if tests exist before allowing writes to production code.
- Warns (doesn't block) if no test file found
- Tracks TDD compliance metrics
- Only checks strategies/ and similar production paths
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Paths that require tests
PRODUCTION_PATHS = [
    "strategies/",
    "src/",
    "lib/",
    "app/",
    "core/",
    "services/",
    "models/",
    "handlers/",
    "controllers/",
    "utils/",
    "helpers/",
]

# Paths to skip (tests, docs, config)
SKIP_PATHS = [
    "tests/",
    "test_",
    "__pycache__",
    ".pytest_cache",
    "docs/",
    ".claude/",
    "specs/",
    "config/",
    ".planning/",
    "scripts/",
    "migrations/",
    "fixtures/",
]

# Environment variable to control blocking behavior
# Set TDD_GUARD_MODE=warn to only warn (default: block)
BLOCKING_MODE = os.environ.get("TDD_GUARD_MODE", "block") == "block"

# Extensions that need tests
CODE_EXTENSIONS = {".py", ".rs", ".ts", ".js"}

# Metrics storage
METRICS_DIR = Path.home() / ".claude" / "metrics"
TDD_LOG = METRICS_DIR / "tdd_compliance.jsonl"


def get_project_name() -> str:
    """Get project name from git repo or environment."""
    env_name = os.environ.get("CLAUDE_PROJECT_NAME", "")
    if env_name and env_name != "unknown":
        return env_name
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except Exception:
        pass
    return Path.cwd().name


def log_tdd_metric(data: dict):
    """Log TDD compliance metric."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "project": get_project_name(),
        **data,
    }
    with open(TDD_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def should_check_file(file_path: str) -> bool:
    """Determine if this file needs TDD check."""
    path = Path(file_path)

    # Skip non-code files
    if path.suffix not in CODE_EXTENSIONS:
        return False

    # Skip test files and other non-production paths
    path_str = str(path).lower()
    for skip in SKIP_PATHS:
        if skip in path_str:
            return False

    # Check if in production path
    return any(prod_path in path_str for prod_path in PRODUCTION_PATHS)


def find_test_file(file_path: str) -> Path | None:
    """Find corresponding test file for a source file."""
    path = Path(file_path)
    base_name = path.stem
    parent = path.parent

    # Common test file patterns
    test_patterns = [
        f"test_{base_name}.py",
        f"{base_name}_test.py",
        f"tests/test_{base_name}.py",
        f"tests/{base_name}_test.py",
        f"../tests/test_{base_name}.py",
        f"../../tests/test_{base_name}.py",
        f"../../tests/strategies/test_{base_name}.py",
    ]

    # Check each pattern
    for pattern in test_patterns:
        test_path = parent / pattern
        if test_path.exists():
            return test_path

    # Check in project tests/ directory
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    for tests_dir in ["tests", "test"]:
        test_dir = project_dir / tests_dir
        if test_dir.exists():
            # Search recursively
            for test_file in test_dir.rglob(f"test_{base_name}.py"):
                return test_file
            for test_file in test_dir.rglob(f"{base_name}_test.py"):
                return test_file

    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only check Write/Edit operations
    if tool_name not in ["Write", "Edit", "MultiEdit"]:
        print(json.dumps({}))
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path:
        print(json.dumps({}))
        sys.exit(0)

    # Check if this file needs TDD verification
    if not should_check_file(file_path):
        log_tdd_metric(
            {
                "type": "skip",
                "file": file_path,
                "reason": "not_production_code",
            }
        )
        print(json.dumps({}))
        sys.exit(0)

    # Look for corresponding test file
    test_file = find_test_file(file_path)

    if test_file:
        # Test exists - good!
        log_tdd_metric(
            {
                "type": "compliant",
                "file": file_path,
                "test_file": str(test_file),
            }
        )
        print(json.dumps({}))
        sys.exit(0)

    # No test found - block or warn based on mode
    log_tdd_metric(
        {
            "type": "violation",
            "file": file_path,
            "test_file": None,
            "blocked": BLOCKING_MODE,
        }
    )

    # Generate message
    base_name = Path(file_path).stem

    if BLOCKING_MODE:
        # BLOCK the operation
        block_message = f"""
🚫 **TDD VIOLATION**: No test file found for `{Path(file_path).name}`

Expected test file patterns:
- `tests/test_{base_name}.py`
- `tests/strategies/test_{base_name}.py`
- `test_{base_name}.py` (same directory)

**Action Required**: Write the test FIRST (Red phase), then implement.

To bypass: Set TDD_GUARD_MODE=warn in environment.
"""
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "decision": "block",
                "reason": block_message,
            }
        }
        print(json.dumps(output))
        sys.exit(1)  # Non-zero exit to block
    else:
        # Warn only
        warning = f"""
⚠️ **TDD Warning**: No test file found for `{Path(file_path).name}`

Expected test file patterns:
- `tests/test_{base_name}.py`
- `tests/strategies/test_{base_name}.py`
- `test_{base_name}.py` (same directory)

**TDD Best Practice**: Write failing test BEFORE production code.
"""
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "notification": warning,
            }
        }
        print(json.dumps(output))
        sys.exit(0)


if __name__ == "__main__":
    main()
