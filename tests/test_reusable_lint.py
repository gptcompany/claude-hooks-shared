"""The failure path of the reusable lint job must print findings with an output format ruff still supports."""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "_reusable-lint.yml"


def _run_scripts() -> list[str]:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    return [step["run"] for step in jobs["lint"]["steps"] if "run" in step]


def test_ruff_failure_listing_uses_a_supported_output_format():
    scripts = "\n".join(_run_scripts())
    assert "--output-format=text" not in scripts  # removed from ruff: the listing used to die with exit 2
    assert "--output-format=concise" in scripts
