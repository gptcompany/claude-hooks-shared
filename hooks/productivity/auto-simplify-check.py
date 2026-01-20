#!/usr/bin/env python3
"""Auto-Simplify Check Hook - Suggests code simplification at session end.

Runs on Stop event. Checks if any modified files exceed complexity thresholds
and suggests running code-simplifier agent.

Hook type: Stop
"""

import json
import subprocess
import sys
from pathlib import Path

# Thresholds
MAX_FILE_LINES = 200
MAX_FUNCTIONS = 10
CODE_EXTENSIONS = {".py", ".ts", ".js", ".tsx", ".jsx"}


def get_modified_files() -> list[str]:
    """Get code files modified in recent commits or working tree."""
    try:
        # Check working tree changes first
        result = subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True, timeout=5)
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # Also check staged changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        staged = result.stdout.strip().split("\n") if result.stdout.strip() else []
        files.extend(staged)

        # Also check last commit (in case already committed)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        committed = result.stdout.strip().split("\n") if result.stdout.strip() else []
        files.extend(committed)

        # Filter to code files only
        code_files = []
        for f in set(files):
            if f and Path(f).suffix in CODE_EXTENSIONS and Path(f).exists():
                code_files.append(f)

        return code_files
    except Exception:
        return []


def check_complexity(filepath: str) -> dict:
    """Quick complexity check for a file."""
    try:
        path = Path(filepath)
        if not path.exists():
            return {"complex": False}

        content = path.read_text()
        lines = content.split("\n")
        line_count = len(lines)

        # Count function/class definitions (rough heuristic)
        func_patterns = ["def ", "async def ", "function ", "const ", "class "]
        func_count = sum(1 for line in lines if any(p in line for p in func_patterns))

        # Check if complex
        is_complex = line_count > MAX_FILE_LINES or func_count > MAX_FUNCTIONS

        return {
            "complex": is_complex,
            "lines": line_count,
            "functions": func_count,
            "file": filepath,
        }
    except Exception:
        return {"complex": False}


def main():
    """Main entry point."""
    # Read hook input (not used but required)
    hook_input = {}
    if not sys.stdin.isatty():
        try:
            hook_input = json.load(sys.stdin)
        except json.JSONDecodeError:
            pass

    # Get modified code files
    modified_files = get_modified_files()

    if not modified_files:
        print(json.dumps({}))
        return

    # Check complexity of each
    complex_files = []
    for f in modified_files:
        result = check_complexity(f)
        if result.get("complex"):
            complex_files.append(result)

    if not complex_files:
        print(json.dumps({}))
        return

    # Build suggestion message
    files_summary = "\n".join(
        f"  - {r['file']}: {r['lines']} lines, ~{r['functions']} functions"
        for r in complex_files[:5]  # Max 5 files in message
    )

    suggestion = f"""[Code Complexity] {len(complex_files)} file(s) may benefit from simplification:
{files_summary}

Consider running: Task(subagent_type="code-simplifier") on these files."""

    # Output as additionalContext for next session
    # Save to file for tips-auto-inject to pick up
    tips_file = Path("/tmp/claude-metrics/simplify-suggestion.txt")
    tips_file.parent.mkdir(parents=True, exist_ok=True)
    tips_file.write_text(suggestion)

    # Also output for current session end
    print(json.dumps({"additionalContext": suggestion}))


if __name__ == "__main__":
    main()
