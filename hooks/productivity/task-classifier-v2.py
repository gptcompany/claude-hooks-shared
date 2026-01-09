#!/usr/bin/env python3
"""
Task Classifier v2 - FIXED for Claude Code UserPromptSubmit

Valid UserPromptSubmit outputs:
- decision: "block" + reason (stops prompt, shows reason to user)
- hookSpecificOutput.modifiedUserPrompt (modifies the prompt)
- hookSpecificOutput.additionalContext (adds context to conversation)
- Plain stdout text (added as context)
- stderr (shown to user in verbose mode, NOT added to context)
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

METRICS_DIR = Path.home() / ".claude" / "metrics"
CLASSIFIER_LOG = METRICS_DIR / "task_classifier.jsonl"
RALPH_STATE = Path.home() / ".claude" / "ralph" / "state.json"

# Classification keywords (base weights)
RALPH_KEYWORDS = {
    "fix all": 0.9,
    "fix lint": 0.9,
    "fix type errors": 0.9,
    "fix mypy": 0.9,
    "update all": 0.8,
    "rename all": 0.8,
    "refactor": 0.7,
    "migrate": 0.7,
    "add tests for": 0.7,
    "increase coverage": 0.7,
    "generate docs": 0.6,
    "fix": 0.4,
    "debug": 0.4,
    "update": 0.3,
}

SPECIALIST_KEYWORDS = {
    "strategy": 0.8,
    "nautilus": 0.9,
    "backtest": 0.8,
    "indicator": 0.7,
    "trading": 0.6,
    "research": 0.7,
    "paper": 0.7,
    "dashboard": 0.7,
    "grafana": 0.8,
}

ALPHA_EVOLVE_KEYWORDS = {
    "design": 0.7,
    "architect": 0.8,
    "multiple approaches": 0.9,
    "compare options": 0.8,
    "create new": 0.6,
    "implement new": 0.5,
}

COMPLEXITY_INDICATORS = {
    "architecture": 0.3,
    "design decision": 0.4,
    "trade-off": 0.3,
    "best approach": 0.3,
    "recommend": 0.2,
    "creative": 0.4,
}


# =============================================================================
# Classification
# =============================================================================


def calculate_complexity(prompt: str) -> float:
    prompt_lower = prompt.lower()
    complexity = sum(w for k, w in COMPLEXITY_INDICATORS.items() if k in prompt_lower)
    word_count = len(prompt.split())
    if word_count > 100:
        complexity += 0.2
    elif word_count > 50:
        complexity += 0.1
    complexity += prompt.count("?") * 0.1
    return min(1.0, complexity)


def classify_task(prompt: str) -> tuple[str, float, list[str], float]:
    """Returns (mode, confidence, keywords, complexity)"""
    prompt_lower = prompt.lower()
    complexity = calculate_complexity(prompt)

    # Score each mode
    ralph_score, ralph_kw = 0.0, []
    for kw, w in RALPH_KEYWORDS.items():
        if kw in prompt_lower:
            ralph_score += w
            ralph_kw.append(kw)

    specialist_score, specialist_kw = 0.0, []
    for kw, w in SPECIALIST_KEYWORDS.items():
        if kw in prompt_lower:
            specialist_score += w
            specialist_kw.append(kw)

    evolve_score, evolve_kw = 0.0, []
    for kw, w in ALPHA_EVOLVE_KEYWORDS.items():
        if kw in prompt_lower:
            evolve_score += w
            evolve_kw.append(kw)

    # Complexity penalty for Ralph
    ralph_score *= 1.0 - complexity * 0.5

    scores = {
        "ralph": (ralph_score, ralph_kw),
        "specialist": (specialist_score, specialist_kw),
        "alpha-evolve": (evolve_score, evolve_kw),
    }

    best = max(scores, key=lambda k: scores[k][0])
    score, kws = scores[best]

    if score < 0.3:
        return "standard", 0.0, [], complexity

    return best, min(1.0, score / 2.0), kws, complexity


# =============================================================================
# Main Hook
# =============================================================================


def notify_user(message: str):
    """Print to stderr so user sees the notification."""
    print(message, file=sys.stderr)


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    prompt = input_data.get("prompt", "")
    prompt_lower = prompt.lower().strip()

    # Escape commands
    if prompt_lower == "stop ralph":
        try:
            if RALPH_STATE.exists():
                state = json.loads(RALPH_STATE.read_text())
                state["active"] = False
                RALPH_STATE.write_text(json.dumps(state, indent=2))
        except (json.JSONDecodeError, OSError):
            pass  # State file corrupted, ignore
        notify_user("[Task Classifier] Ralph mode deactivated.")
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": "[SYSTEM] Ralph mode deactivated by user.",
                    }
                }
            )
        )
        sys.exit(0)

    if prompt_lower == "ralph status":
        status = "not active"
        try:
            if RALPH_STATE.exists():
                state = json.loads(RALPH_STATE.read_text())
                if state.get("active"):
                    status = f"active, iteration {state.get('iteration', 0)}/15"
        except (json.JSONDecodeError, OSError):
            status = "unknown (state file error)"
        notify_user(f"[Task Classifier] Ralph status: {status}")
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": f"[SYSTEM] Ralph status: {status}",
                    }
                }
            )
        )
        sys.exit(0)

    # Skip short prompts
    if len(prompt.split()) < 3:
        sys.exit(0)

    # Skip if already in Ralph
    if RALPH_STATE.exists():
        try:
            state = json.loads(RALPH_STATE.read_text())
            if state.get("active"):
                sys.exit(0)
        except (json.JSONDecodeError, OSError):
            pass

    # Classify
    mode, confidence, keywords, complexity = classify_task(prompt)

    # Log
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    with open(CLASSIFIER_LOG, "a") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.now().isoformat(),
                    "mode": mode,
                    "conf": confidence,
                    "complex": complexity,
                    "kw": keywords[:5],
                }
            )
            + "\n"
        )

    # Standard - no modification
    if mode == "standard":
        sys.exit(0)

    # For Ralph with high confidence - auto-activate with modified prompt
    if mode == "ralph" and confidence >= 0.6 and complexity < 0.4:
        RALPH_STATE.parent.mkdir(parents=True, exist_ok=True)
        RALPH_STATE.write_text(
            json.dumps(
                {
                    "active": True,
                    "original_prompt": prompt,
                    "iteration": 0,
                    "started_at": datetime.now().isoformat(),
                    "keywords": keywords,
                },
                indent=2,
            )
        )

        # NOTIFY USER about Ralph activation
        notify_user(
            f"[Task Classifier] Ralph mode AUTO-ACTIVATED (confidence: {confidence:.0%}, keywords: {', '.join(keywords[:3])})"
        )

        enhanced = f"""{prompt}

## Ralph Mode Active (auto-triggered: confidence {confidence:.0%})

### Exit Criteria (ALL must pass)
- All tests pass: `uv run pytest tests/ -x`
- No lint errors: `uv run ruff check .`
- Task completed as described

### Circuit Breakers
- Max 15 iterations | Stop on 3 errors | Stop on 5 no-progress

Type "STOP RALPH" to exit | "RALPH STATUS" for info
"""
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "modifiedUserPrompt": enhanced,
                    }
                }
            )
        )
        sys.exit(0)

    # For lower confidence or other modes - add context (not block)
    mode_info = {
        "ralph": f"Task appears mechanical (Ralph candidate). Keywords: {', '.join(keywords[:3])}. Say 'use ralph mode' to activate.",
        "specialist": f"Specialist task detected. Keywords: {', '.join(keywords[:3])}",
        "alpha-evolve": f"Design task detected. Consider multiple approaches. Keywords: {', '.join(keywords[:3])}",
    }

    context = mode_info.get(mode, "")
    if context:
        # NOTIFY USER about classification
        notify_user(
            f"[Task Classifier] Mode: {mode.upper()} (confidence: {confidence:.0%}) - {context}"
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": f"[Task Classification] {context}",
                    }
                }
            )
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
