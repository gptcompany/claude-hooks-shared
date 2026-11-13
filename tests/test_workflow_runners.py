"""Regola operatore del 13/11/2026: nessun job dipende dai runner GitHub hosted.

Repo pubblico: i job raggiungibili da una PR, e i reusable che i chiamanti invocano dalle loro PR, usano la
guardia che lascia le PR da fork su ubuntu-latest, così il codice da fork non arriva mai ai runner self-hosted.
"""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
FORK_PR = (
    "(github.event_name == 'pull_request' || github.event_name == 'pull_request_review')"
    " && github.event.pull_request.head.repo.full_name != github.repository && 'ubuntu-latest'"
)
GUARDED = "${{ " + FORK_PR + " || vars.CI_RUNS_ON || 'sg-ci' }}"
TRUSTED = "${{ vars.CI_RUNS_ON || 'sg-ci' }}"
# A called workflow runs in the caller's event context, so it may serve a caller's pull request.
UNTRUSTED_EVENTS = {"pull_request", "pull_request_target", "pull_request_review", "workflow_call"}


def _triggers(data: dict) -> set[str]:
    on = data.get("on", data.get(True))  # PyYAML reads a bare `on` key as True.
    if isinstance(on, str):
        return {on}
    return set(on)


def test_every_job_uses_a_self_hosted_selector():
    seen = 0
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        allowed = {GUARDED} if UNTRUSTED_EVENTS & _triggers(data) else {GUARDED, TRUSTED}
        for name, spec in data.get("jobs", {}).items():
            if "runs-on" in spec:
                seen += 1
                assert spec["runs-on"] in allowed, f"{path.name}:{name} usa {spec['runs-on']}"
    assert seen >= 6
