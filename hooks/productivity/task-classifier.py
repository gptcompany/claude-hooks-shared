#!/usr/bin/env python3
"""
UserPromptSubmit Hook: Task Classifier + Prompt Optimizer

Classifies tasks into execution modes and optimizes prompts accordingly:
- ralph: Mechanical, iterative tasks (bug fixes, refactors, test coverage)
- specialist: Domain-specific tasks (NT strategies, research)
- alpha-evolve: Creative tasks requiring multiple approaches
- standard: Default single-pass execution

Integrates with existing prompt-optimizer for model-aware optimization.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

# Task classification keywords
RALPH_KEYWORDS = {
    # Bug fixes
    "fix",
    "fix all",
    "debug",
    "resolve",
    # Refactoring
    "refactor",
    "rename",
    "reorganize",
    "restructure",
    # Migrations
    "migrate",
    "upgrade",
    "update all",
    "convert all",
    # Test coverage
    "add tests",
    "test coverage",
    "write tests",
    "increase coverage",
    # Documentation
    "generate docs",
    "add docstrings",
    "document all",
    # Linting/formatting
    "lint",
    "format",
    "fix lint",
    "fix type errors",
    "fix mypy",
    # Cleanup
    "remove unused",
    "delete dead",
    "clean up",
}

SPECIALIST_KEYWORDS = {
    # NautilusTrader specific
    "strategy",
    "nautilus",
    "backtest",
    "indicator",
    "trading",
    "position size",
    "risk management",
    "order",
    "execution",
    # Research
    "research",
    "paper",
    "academic",
    "analyze paper",
    # Visualization
    "dashboard",
    "grafana",
    "chart",
    "visualization",
    # Data
    "catalog",
    "parquet",
    "data pipeline",
}

ALPHA_EVOLVE_KEYWORDS = {
    # Creative/architectural
    "design",
    "architect",
    "create new",
    "implement new",
    # Multiple approaches
    "approaches",
    "alternatives",
    "compare",
    "evaluate options",
    # Complex algorithms
    "optimize algorithm",
    "improve performance",
    "complex",
    # Feature development
    "new feature",
    "add feature",
}

# Ralph mode configuration
RALPH_CONFIG = {
    "max_iterations": 15,
    "exit_on_tests_pass": True,
    "exit_on_no_errors": True,
    "circuit_breaker": {
        "max_consecutive_errors": 3,
        "max_no_progress": 5,
    },
}

# Metrics storage
METRICS_DIR = Path.home() / ".claude" / "metrics"
CLASSIFIER_LOG = METRICS_DIR / "task_classifier.jsonl"
RALPH_STATE = Path.home() / ".claude" / "ralph" / "state.json"


# =============================================================================
# Task Classification
# =============================================================================


def classify_task(prompt: str) -> tuple[str, float, list[str]]:
    """
    Classify task into execution mode.

    Returns:
        (mode, confidence, matched_keywords)
    """
    prompt_lower = prompt.lower()

    # Check for Ralph keywords
    ralph_matches = [kw for kw in RALPH_KEYWORDS if kw in prompt_lower]
    ralph_score = len(ralph_matches) / max(len(RALPH_KEYWORDS), 1)

    # Check for Specialist keywords
    specialist_matches = [kw for kw in SPECIALIST_KEYWORDS if kw in prompt_lower]
    specialist_score = len(specialist_matches) / max(len(SPECIALIST_KEYWORDS), 1)

    # Check for AlphaEvolve keywords
    evolve_matches = [kw for kw in ALPHA_EVOLVE_KEYWORDS if kw in prompt_lower]
    evolve_score = len(evolve_matches) / max(len(ALPHA_EVOLVE_KEYWORDS), 1)

    # Boost scores based on strong indicators
    if any(phrase in prompt_lower for phrase in ["fix all", "update all", "convert all"]):
        ralph_score += 0.3
    if any(phrase in prompt_lower for phrase in ["nautilus", "trading strategy"]):
        specialist_score += 0.3
    if any(phrase in prompt_lower for phrase in ["multiple approaches", "compare options"]):
        evolve_score += 0.3

    # Determine winner
    scores = {
        "ralph": (ralph_score, ralph_matches),
        "specialist": (specialist_score, specialist_matches),
        "alpha-evolve": (evolve_score, evolve_matches),
    }

    # Need minimum threshold to classify
    MIN_THRESHOLD = 0.05

    best_mode = max(scores, key=lambda k: scores[k][0])
    best_score, best_matches = scores[best_mode]

    if best_score < MIN_THRESHOLD:
        return "standard", 0.0, []

    # Normalize confidence to 0-1
    confidence = min(1.0, best_score * 3)  # Scale up for visibility

    return best_mode, confidence, best_matches


def enhance_prompt_for_mode(prompt: str, mode: str) -> str:
    """Enhance prompt with mode-specific instructions."""

    if mode == "ralph":
        return f"""{prompt}

## Ralph Mode Instructions
- Work iteratively until ALL criteria met
- Commit progress after each significant change
- Update progress tracking

## Exit Criteria
- All tests pass (pytest)
- No lint errors (ruff check .)
- No type errors (mypy)
- Task explicitly completed

## Circuit Breaker
- Stop after {RALPH_CONFIG["max_iterations"]} iterations
- Stop if same error appears 3 times
- Stop if no progress for 5 iterations
"""

    elif mode == "specialist":
        return f"""{prompt}

## Specialist Mode
Use appropriate specialist agent:
- nautilus-coder: For NT strategy implementation
- strategy-researcher: For academic paper analysis
- grafana-expert: For dashboard creation

Search Context7 and Discord before implementing.
"""

    elif mode == "alpha-evolve":
        return f"""{prompt}

## Alpha-Evolve Mode
Generate multiple implementation approaches:
1. Create 2-3 distinct implementations
2. Evaluate fitness of each
3. Select best or create ensemble
4. Document trade-offs

Use [E] marker in task title for tracking.
"""

    return prompt


# =============================================================================
# Ralph State Management
# =============================================================================


def init_ralph_state(prompt: str, mode: str) -> dict:
    """Initialize Ralph state for tracking."""
    RALPH_STATE.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "active": mode == "ralph",
        "original_prompt": prompt,
        "mode": mode,
        "iteration": 0,
        "started_at": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat(),
        "consecutive_errors": 0,
        "consecutive_no_progress": 0,
        "progress": [],
        "exit_reason": None,
    }

    RALPH_STATE.write_text(json.dumps(state, indent=2))
    return state


def get_ralph_state() -> dict | None:
    """Get current Ralph state if active."""
    if not RALPH_STATE.exists():
        return None

    try:
        state = json.loads(RALPH_STATE.read_text())
        if state.get("active"):
            return state
    except (json.JSONDecodeError, OSError):
        pass

    return None


# =============================================================================
# Logging
# =============================================================================


def log_classification(data: dict):
    """Log task classification metrics."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "classification",
        **data,
    }

    with open(CLASSIFIER_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# =============================================================================
# Main Hook
# =============================================================================


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({}))
        sys.exit(0)

    user_prompt = input_data.get("prompt", "")

    # Skip short prompts (likely commands or confirmations)
    if len(user_prompt.split()) < 3:
        print(json.dumps({}))
        sys.exit(0)

    # Check if Ralph mode is already active
    ralph_state = get_ralph_state()
    if ralph_state:
        # In Ralph mode - don't re-classify, let stop hook handle
        print(json.dumps({}))
        sys.exit(0)

    # Classify task
    mode, confidence, matches = classify_task(user_prompt)

    # Log classification
    log_classification(
        {
            "prompt": user_prompt[:500],
            "mode": mode,
            "confidence": confidence,
            "matched_keywords": matches,
            "prompt_length": len(user_prompt.split()),
        }
    )

    # If standard mode, just pass through
    if mode == "standard":
        print(json.dumps({}))
        sys.exit(0)

    # Initialize Ralph state if entering Ralph mode
    if mode == "ralph":
        init_ralph_state(user_prompt, mode)

    # Enhance prompt for mode
    enhanced_prompt = enhance_prompt_for_mode(user_prompt, mode)

    # Build notification
    mode_icons = {
        "ralph": "🔄",
        "specialist": "🎯",
        "alpha-evolve": "🧬",
    }

    notification = f"""
{mode_icons.get(mode, "📋")} **Task Classification**: {mode.upper()} mode
Confidence: {confidence:.0%} | Keywords: {", ".join(matches[:5])}
"""

    if mode == "ralph":
        notification += f"""
Ralph Loop activated:
- Max iterations: {RALPH_CONFIG["max_iterations"]}
- Exit on: tests pass, no errors
- Progress tracked in ~/.claude/ralph/
"""

    # Return enhanced prompt
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "modifiedUserPrompt": enhanced_prompt,
        },
        "notification": notification,
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
