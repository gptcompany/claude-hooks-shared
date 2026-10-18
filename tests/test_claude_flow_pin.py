"""claude-flow is pinned to one exact version in every hook, never `@latest` (F-229)."""

import ast
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^claude-flow@\d+\.\d+\.\d+$")


def _specs() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted((ROOT / "hooks").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("claude-flow@"):
                found.setdefault(str(path.relative_to(ROOT)), []).append(node.value)
    return found


def test_every_claude_flow_spec_is_an_exact_version_and_the_same_one():
    specs = _specs()
    assert len(specs) >= 6, specs
    values = {value for found in specs.values() for value in found}
    assert all(SEMVER.match(value) for value in values), values
    assert len(values) == 1, values


def test_unit_tests_run_with_the_offline_npx_stub(offline_npx: Path):
    assert shutil.which("npx") == str(offline_npx)
    result = subprocess.run(["npx", "-y", "claude-flow@0.0.0"], capture_output=True, text=True, timeout=5)
    assert result.returncode == 1 and "stubbed" in result.stderr
