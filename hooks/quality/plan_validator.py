#!/usr/bin/env python3
"""Auto-validate plans with PMW checks."""

import json
import re
import sys
from pathlib import Path


def validate_plan(content: str) -> list[str]:
    """Return list of issues found."""
    issues = []

    # PMW 1: Too many classes/complexity
    class_count = len(re.findall(r"^class \w+", content, re.M))
    if class_count > 3:
        issues.append(f"COMPLEXITY: {class_count} classes - consider simplifying")

    # PMW 2: Subprocess calls without cache
    if "subprocess.run" in content and "cache" not in content.lower():
        issues.append("PERF: subprocess calls without caching")

    # PMW 3: Assumes data that might not exist
    assumed_files = re.findall(r'Path.*?/\s*"([^"]+\.json)"', content)
    for f in assumed_files:
        if not (Path.home() / ".claude" / "metrics" / f).exists():
            issues.append(f"MISSING: assumes {f} exists")

    # PMW 4: Lines of code estimate
    code_blocks = re.findall(r"```python\n(.*?)```", content, re.S)
    total_lines = sum(len(b.split("\n")) for b in code_blocks)
    if total_lines > 200:
        issues.append(f"SIZE: ~{total_lines} lines - KISS violation?")

    return issues


def main():
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")

        # Only validate plan files
        if "/plans/" not in file_path or not file_path.endswith(".md"):
            sys.exit(0)

        content = tool_input.get("content", "")
        issues = validate_plan(content)

        if issues:
            msg = "Plan validation:\n" + "\n".join(f"  - {i}" for i in issues)
            print(json.dumps({"systemMessage": msg}))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
