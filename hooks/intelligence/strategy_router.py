#!/usr/bin/env python3
"""Strategy Router v2: State Machine + PMW Fixes."""

import json
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path


class Phase(Enum):
    DEV = "DEV"
    TEST = "TEST"
    REVIEW = "REVIEW"
    DEPLOY = "DEPLOY"
    MONITOR = "MONITOR"


METRICS = Path.home() / ".claude" / "metrics"
CACHE_FILE = METRICS / "gh_cache.json"
CACHE_TTL = 30  # seconds


def cached_gh(cmd: list[str]) -> dict | None:
    """Cached gh CLI call."""
    cache_key = " ".join(cmd)
    try:
        if CACHE_FILE.exists():
            cache = json.loads(CACHE_FILE.read_text())
            if cache.get("key") == cache_key and time.time() - cache.get("ts", 0) < CACHE_TTL:
                return cache.get("data")
    except Exception:
        pass

    try:
        r = subprocess.run(["gh"] + cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            data = json.loads(r.stdout) if r.stdout.strip() else None
            CACHE_FILE.write_text(json.dumps({"key": cache_key, "ts": time.time(), "data": data}))
            return data
    except Exception:
        pass
    return None


def get_phase_and_directive() -> tuple[Phase, str | None]:
    """Get current phase and directive."""
    # Load metrics
    state = {}
    try:
        state = json.loads((METRICS / "session_state.json").read_text())
    except Exception:
        pass

    edits = {}
    try:
        edits = json.loads((METRICS / "file_edits.json").read_text())
    except Exception:
        pass

    errors = state.get("errors", 0)
    calls = max(state.get("tool_calls", 1), 1)
    error_rate = errors / calls

    # Thrashing detection (PMW fix: use existing file_edits.json)
    thrashing = [Path(f).name for f, v in edits.items() if v.get("rework_count", 0) >= 5]

    # GitHub state (cached)
    pr = cached_gh(["pr", "view", "--json", "number,state,reviewDecision"])
    ci = cached_gh(["run", "list", "--limit", "1", "--json", "status,conclusion"])

    pr_state = pr.get("state", "").lower() if pr else "none"
    pr_num = pr.get("number", 0) if pr else 0
    review = pr.get("reviewDecision", "") if pr else ""
    ci_status = "unknown"
    if ci and isinstance(ci, list) and len(ci) > 0 and ci[0].get("status") == "completed":
        ci_status = "pass" if ci[0].get("conclusion") == "success" else "fail"

    # Phase inference
    phase = Phase.DEV
    if pr_state == "open" and review == "REVIEW_REQUIRED":
        phase = Phase.REVIEW
    elif ci_status == "fail":
        phase = Phase.TEST
    elif pr_state == "open" and review == "APPROVED":
        phase = Phase.DEPLOY
    elif pr_state == "merged":
        phase = Phase.MONITOR

    # Directives (priority order)
    if ci_status == "fail" and pr_state == "none":
        return phase, "[TEST] CI failing → git stash && fix CI"
    if review == "CHANGES_REQUESTED":
        return phase, f"[REVIEW] PR #{pr_num} blocked → address comments"
    if error_rate > 0.25 and calls > 10:
        return phase, "[DEBUG] Error rate 25%+ → /undo:checkpoint"
    if thrashing:
        return phase, f"[DEV] {thrashing[0]} edited 5x+ → step back"
    if review == "REVIEW_REQUIRED":
        return phase, f"[REVIEW] PR #{pr_num} → awaiting review"

    return phase, None


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    phase, directive = get_phase_and_directive()

    # Save phase state
    try:
        METRICS.mkdir(parents=True, exist_ok=True)
        (METRICS / "strategy_state.json").write_text(json.dumps({"phase": phase.value}))
    except Exception:
        pass

    if directive:
        print(json.dumps({"systemMessage": directive}))
    sys.exit(0)


if __name__ == "__main__":
    main()
