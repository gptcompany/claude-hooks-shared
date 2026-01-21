#!/usr/bin/env python3
"""
Post-Commit Quality Hook for Claude Code

Triggers after successful git commit to:
1. Check complexity of modified files
2. Run pyright on Python files
3. Emit instructions to spawn code-simplifier or Ralph agents

Hook Type: PostToolUse (Bash)
Trigger: git commit success
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Configuration
COMPLEXITY_THRESHOLDS = {
    "max_lines": 200,
    "max_functions": 10,
}

# File extensions to check
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".sh", ".bash"}
PYTHON_EXTENSIONS = {".py"}
TYPESCRIPT_EXTENSIONS = {".ts", ".tsx"}

# Metrics logging
METRICS_DIR = Path.home() / ".claude" / "metrics"
QUALITY_LOG = METRICS_DIR / "post_commit_quality.jsonl"


def log_event(event_type: str, data: dict):
    """Log quality check events."""
    from datetime import datetime

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        **data,
    }
    with open(QUALITY_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def is_commit_command(command: str) -> bool:
    """Check if command is a git commit."""
    return bool(re.search(r"\bgit\s+commit\b", command))


def commit_succeeded(tool_result: str) -> bool:
    """Check if commit succeeded (not amend, not failed)."""
    # Failed commits
    if "nothing to commit" in tool_result.lower():
        return False
    if "error:" in tool_result.lower():
        return False
    if "fatal:" in tool_result.lower():
        return False
    # Success patterns
    if re.search(r"\[\w+\s+[a-f0-9]+\]", tool_result):  # [branch hash] pattern
        return True
    if "create mode" in tool_result.lower():
        return True
    if "files changed" in tool_result.lower():
        return True
    return False


def get_modified_files() -> list[str]:
    """Get list of files modified in the last commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
    except Exception:
        pass
    return []


def get_cwd() -> Path:
    """Get current working directory from environment."""
    cwd = os.environ.get("CLAUDE_WORKING_DIR", os.getcwd())
    return Path(cwd)


def check_file_complexity(file_path: Path) -> dict:
    """Check complexity metrics for a file."""
    result = {
        "path": str(file_path),
        "lines": 0,
        "functions": 0,
        "exceeds_threshold": False,
        "reasons": [],
    }

    if not file_path.exists():
        return result

    try:
        content = file_path.read_text()
        lines = content.split("\n")
        result["lines"] = len(lines)

        # Count functions/methods
        if file_path.suffix in PYTHON_EXTENSIONS:
            # Python: def, async def, class
            result["functions"] = len(
                re.findall(r"^\s*(def |async def |class )", content, re.MULTILINE)
            )
        elif file_path.suffix in TYPESCRIPT_EXTENSIONS or file_path.suffix in {
            ".js",
            ".jsx",
        }:
            # JS/TS: function, const =>, class
            result["functions"] = len(
                re.findall(
                    r"^\s*(function |const \w+ = |class )", content, re.MULTILINE
                )
            )
        elif file_path.suffix in {".sh", ".bash"}:
            # Bash: function name() or name()
            result["functions"] = len(
                re.findall(r"^\s*(\w+\s*\(\)|function\s+\w+)", content, re.MULTILINE)
            )

        # Check thresholds
        if result["lines"] > COMPLEXITY_THRESHOLDS["max_lines"]:
            result["exceeds_threshold"] = True
            result["reasons"].append(
                f"lines={result['lines']} > {COMPLEXITY_THRESHOLDS['max_lines']}"
            )

        if result["functions"] > COMPLEXITY_THRESHOLDS["max_functions"]:
            result["exceeds_threshold"] = True
            result["reasons"].append(
                f"functions={result['functions']} > {COMPLEXITY_THRESHOLDS['max_functions']}"
            )

    except Exception as e:
        result["error"] = str(e)

    return result


def run_pyright(files: list[Path]) -> dict:
    """Run pyright on Python files and return errors."""
    python_files = [f for f in files if f.suffix in PYTHON_EXTENSIONS and f.exists()]
    if not python_files:
        return {"has_errors": False, "files": [], "error_count": 0}

    result = {
        "has_errors": False,
        "files": [str(f) for f in python_files],
        "error_count": 0,
        "errors": [],
    }

    try:
        proc = subprocess.run(
            ["python3", "-m", "pyright", "--outputjson"]
            + [str(f) for f in python_files],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if proc.returncode != 0:
            try:
                output = json.loads(proc.stdout)
                diagnostics = output.get("generalDiagnostics", [])
                result["error_count"] = len(diagnostics)
                result["has_errors"] = result["error_count"] > 0
                # Take first 5 errors for context
                result["errors"] = [
                    f"{d.get('file', '?')}:{d.get('range', {}).get('start', {}).get('line', '?')}: {d.get('message', '')}"
                    for d in diagnostics[:5]
                ]
            except json.JSONDecodeError:
                # Pyright didn't output JSON, check stderr
                if "error" in proc.stderr.lower():
                    result["has_errors"] = True
                    result["errors"] = [proc.stderr[:200]]

    except FileNotFoundError:
        # pyright not installed
        pass
    except subprocess.TimeoutExpired:
        result["timeout"] = True
    except Exception as e:
        result["error"] = str(e)

    return result


def generate_quality_message(complex_files: list[dict], pyright_result: dict) -> str:
    """Generate instruction message for Claude."""
    parts = []

    if complex_files:
        file_list = ", ".join([f["path"] for f in complex_files])
        reasons = "; ".join(
            [f"{f['path']}: {', '.join(f['reasons'])}" for f in complex_files]
        )
        parts.append(f"""
**Code Complexity Alert** - The following files exceed complexity thresholds:

Files: `{file_list}`
Details: {reasons}

**Action Required:** Use the `code-simplifier` agent to simplify these files:
```
Task(subagent_type="code-simplifier:code-simplifier", prompt="Simplify the recently modified code in: {file_list}")
```
""")

    if pyright_result.get("has_errors"):
        error_list = "\n".join(pyright_result.get("errors", []))
        parts.append(f"""
**Type Errors Detected** - Pyright found {pyright_result["error_count"]} error(s):

```
{error_list}
```

**Action Required:** Fix the type errors. Consider using Ralph mode for mechanical fixes:
```
use ralph mode to fix pyright errors in: {", ".join(pyright_result["files"])}
```
""")

    if parts:
        return "\n---\n".join(parts)
    return ""


def main():
    """Main hook entry point."""
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Check if this is a Bash tool use
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    # Get command and output
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    tool_result = input_data.get("tool_result", "")

    # Check if it's a git commit command
    if not is_commit_command(command):
        sys.exit(0)

    # Check if commit succeeded
    if not commit_succeeded(tool_result):
        sys.exit(0)

    # Get modified files
    modified_files = get_modified_files()
    if not modified_files:
        sys.exit(0)

    cwd = get_cwd()

    # Filter to code files only
    code_files = []
    for f in modified_files:
        path = cwd / f
        if path.suffix in CODE_EXTENSIONS:
            code_files.append(path)

    if not code_files:
        sys.exit(0)

    # Check complexity
    complex_files = []
    for file_path in code_files:
        complexity = check_file_complexity(file_path)
        if complexity.get("exceeds_threshold"):
            complex_files.append(complexity)

    # Run pyright on Python files
    pyright_result = run_pyright(code_files)

    # Log event
    log_event(
        "post_commit_check",
        {
            "files_checked": len(code_files),
            "complex_files": len(complex_files),
            "pyright_errors": pyright_result.get("error_count", 0),
        },
    )

    # Generate message if needed
    message = generate_quality_message(complex_files, pyright_result)

    if message:
        result = {
            "continue": True,
            "message": f"\n🔍 **Post-Commit Quality Check**\n{message}",
        }
        print(json.dumps(result))
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
