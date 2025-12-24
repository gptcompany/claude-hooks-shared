#!/usr/bin/env python3
"""
Context Preservation Hook: Detects low context and suggests agent delegation.
Runs on Stop event to intelligently decide if Claude should continue or delegate.

This hook helps Claude Code maintain effectiveness by:
1. Estimating current context usage from transcript
2. Warning when context is getting low
3. Suggesting appropriate agents for delegation
"""

import json
import sys
from pathlib import Path


# Agent recommendations based on task patterns
AGENT_SUGGESTIONS = {
    "exploration": ("Explore", "Codebase exploration, finding files/patterns"),
    "debugging": ("alpha-debug", "Iterative bug hunting after implementation"),
    "algorithms": (
        "alpha-evolve",
        "Complex algorithmic tasks, multi-approach generation",
    ),
    "monitoring": (
        "general-purpose",
        "Long-running process monitoring (use run_in_background)",
    ),
    "bitcoin": ("bitcoin-onchain-expert", "Bitcoin Core, ZMQ, RPC integration"),
    "websocket": ("data-streamer", "FastAPI WebSocket, real-time streaming"),
    "visualization": (
        "visualization-renderer",
        "Canvas 2D, Three.js, browser rendering",
    ),
}


def estimate_context_usage(transcript_path: str) -> dict:
    """Estimate context usage from transcript file."""
    try:
        path = Path(transcript_path)
        if not path.exists():
            return {"error": "transcript not found", "estimated_tokens": 0}

        # Read transcript and estimate tokens (4 chars ≈ 1 token)
        content = path.read_text()
        estimated_tokens = len(content) // 4

        # Count messages and tool calls
        lines = content.splitlines()
        messages = sum(
            1 for l in lines if '"type":"human"' in l or '"type":"assistant"' in l
        )
        tool_calls = sum(1 for l in lines if '"tool_name"' in l)

        return {
            "estimated_tokens": estimated_tokens,
            "messages": messages,
            "tool_calls": tool_calls,
            "file_size_kb": path.stat().st_size // 1024,
        }
    except Exception as e:
        return {"error": str(e), "estimated_tokens": 0}


def get_context_percentage(estimated_tokens: int) -> int:
    """Estimate context percentage used (based on ~200k token window)."""
    MAX_CONTEXT = 200000  # Approximate for Claude models
    return min(100, int((estimated_tokens / MAX_CONTEXT) * 100))


def format_agent_suggestions() -> str:
    """Format agent suggestions as readable list."""
    lines = ["Suggested agents for delegation:"]
    for key, (agent, desc) in AGENT_SUGGESTIONS.items():
        lines.append(f"  - {agent}: {desc}")
    return "\n".join(lines)


def main():
    try:
        input_data = json.load(sys.stdin)
        transcript_path = input_data.get("transcript_path", "")

        if not transcript_path:
            sys.exit(0)

        metrics = estimate_context_usage(transcript_path)
        estimated_tokens = metrics.get("estimated_tokens", 0)
        context_pct = get_context_percentage(estimated_tokens)

        # Thresholds
        WARNING_PCT = 60  # Show warning
        CRITICAL_PCT = 80  # Strong delegation suggestion

        if context_pct >= CRITICAL_PCT:
            # Critical: Strong delegation recommendation
            output = {
                "systemMessage": (
                    f"Context at {context_pct}% ({estimated_tokens:,} tokens). "
                    f"RECOMMEND: Delegate remaining tasks to agents.\n\n"
                    f"{format_agent_suggestions()}\n\n"
                    f"Use: Task tool with subagent_type parameter, run_in_background: true for monitoring."
                )
            }
            print(json.dumps(output))
            sys.exit(0)

        elif context_pct >= WARNING_PCT:
            # Warning: Gentle reminder
            output = {
                "systemMessage": (
                    f"Context at {context_pct}%. Consider delegating complex subtasks to agents."
                )
            }
            print(json.dumps(output))
            sys.exit(0)

        # Normal: no action needed
        sys.exit(0)

    except Exception:
        # Fail silently - don't block on hook errors
        sys.exit(0)


if __name__ == "__main__":
    main()
