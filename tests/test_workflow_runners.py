"""Repo pubblico: i workflow girano su runner GitHub-hosted, non sul Dell."""
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def test_no_job_uses_a_self_hosted_runner():
    seen = 0
    for path in sorted(WORKFLOWS.glob("*.yml")):
        jobs = yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs", {})
        for name, spec in jobs.items():
            if "runs-on" in spec:
                seen += 1
                assert spec["runs-on"] == "ubuntu-latest", f"{path.name}:{name}"
    assert seen >= 6
