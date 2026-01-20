#!/usr/bin/env python3
"""
Lesson Injector - UserPromptSubmit Hook

Injects relevant lessons from past sessions using pattern_search.
Lessons are injected based on confidence level:
- HIGH (>0.8): Auto-inject with "[Lessons]" prefix
- MEDIUM (0.5-0.8): Suggest with "Consider:" prefix
- LOW (<0.5): Skip

Input (stdin JSON):
    {"prompt": "user prompt", "cwd": "/path/to/project"}

Output (stdout JSON):
    {"additionalContext": "[Lessons from past sessions]\n- ..."}
"""

import json
import logging
import os
import sys
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "lesson_injector.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Confidence thresholds
CONFIDENCE_HIGH = 0.8
CONFIDENCE_MEDIUM = 0.5
MAX_LESSONS = 3

# Import mcp_client functions with fallback
try:
    from core.mcp_client import get_project_name, pattern_search
except ImportError:
    try:
        # Try relative import for when running as script
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.mcp_client import get_project_name, pattern_search
    except ImportError:
        # Fallback stubs for testing/isolation
        def get_project_name() -> str:
            """Fallback: get project name from cwd."""
            return Path.cwd().name

        def pattern_search(query: str, top_k: int = 3, min_confidence: float = 0.7) -> list[dict]:
            """Fallback: return empty patterns."""
            return []


def extract_context(hook_input: dict) -> tuple[str, str]:
    """Extract prompt and project context from hook input.

    Returns:
        tuple: (prompt, project_name)
    """
    prompt = hook_input.get("prompt", "")
    cwd = hook_input.get("cwd", "")

    # Get project name
    project = get_project_name()
    if not project and cwd:
        project = Path(cwd).name

    return prompt, project


def format_lesson(pattern: dict) -> str | None:
    """Format a pattern as a lesson string based on confidence.

    Args:
        pattern: Pattern dict with 'pattern', 'confidence', etc.

    Returns:
        Formatted lesson string or None if should be skipped.
    """
    confidence = pattern.get("confidence", 0)
    lesson_text = pattern.get("pattern", "")

    if not lesson_text:
        return None

    if confidence < CONFIDENCE_MEDIUM:
        # LOW: Skip
        return None
    elif confidence < CONFIDENCE_HIGH:
        # MEDIUM: Suggest with "Consider:" prefix
        return f"- Consider: {lesson_text}"
    else:
        # HIGH: Auto-inject
        return f"- {lesson_text}"


def process_hook(hook_input: dict) -> dict:
    """Process the hook input and return additionalContext.

    Args:
        hook_input: Dict with 'prompt' and 'cwd'

    Returns:
        Dict with 'additionalContext' or empty dict
    """
    try:
        prompt, project = extract_context(hook_input)

        if not prompt:
            logger.debug("No prompt provided, skipping")
            return {}

        # Build search query from prompt context
        # Use first 100 chars of prompt to focus the search
        search_query = prompt[:100] if len(prompt) > 100 else prompt

        # Search for relevant patterns
        logger.debug(f"Searching patterns for project={project}, query={search_query[:50]}...")
        patterns = pattern_search(
            query=search_query,
            top_k=5,  # Get a few more to filter
            min_confidence=CONFIDENCE_MEDIUM,  # Only medium+ confidence
        )

        if not patterns:
            logger.debug("No patterns found")
            return {}

        # Format lessons
        lessons = []
        for pattern in patterns:
            # Handle both direct pattern dicts and wrapped results
            if isinstance(pattern, dict):
                if "raw" in pattern:
                    # Skip raw output format from pattern_search
                    continue
                lesson = format_lesson(pattern)
                if lesson:
                    lessons.append(lesson)

        if not lessons:
            logger.debug("No lessons after filtering")
            return {}

        # Limit to MAX_LESSONS
        lessons = lessons[:MAX_LESSONS]

        # Build output
        context_lines = ["[Lessons from past sessions]"] + lessons
        additional_context = "\n".join(context_lines)

        logger.info(f"Injecting {len(lessons)} lessons")
        return {"additionalContext": additional_context}

    except Exception as e:
        logger.error(f"Error processing hook: {e}")
        return {}


def main():
    """Main entry point - reads stdin, writes stdout."""
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        print(json.dumps({}))
        sys.exit(0)

    result = process_hook(input_data)
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
