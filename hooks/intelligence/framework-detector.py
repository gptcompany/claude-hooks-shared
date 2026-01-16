#!/usr/bin/env python3
"""
Framework Detector Hook

UserPromptSubmit hook that detects project framework (SpecKit, CGSD, or None)
and injects helpful context into the conversation.

Detection Rules:
- SpecKit: `specs/` directory exists
- CGSD: `.planning/` directory exists
- Both: Both directories exist
- None: Neither exists

Outputs context suggestion for Claude to use appropriate commands.
"""

import contextlib
import json
import os
import sys
from pathlib import Path


def detect_framework(cwd: str) -> dict:
    """Detect framework based on directory structure."""
    cwd_path = Path(cwd)

    # Check for framework indicators
    has_specs = (cwd_path / "specs").exists()
    has_planning = (cwd_path / ".planning").exists()
    has_claude_validation = (cwd_path / ".claude" / "validation").exists()

    # Also check parent directories (in case we're in a subdirectory)
    parent = cwd_path.parent
    while parent != parent.parent:  # Until root
        if (parent / "specs").exists():
            has_specs = True
        if (parent / ".planning").exists():
            has_planning = True
        if (parent / ".claude" / "validation").exists():
            has_claude_validation = True
        parent = parent.parent

    # Determine framework
    frameworks = []
    if has_specs:
        frameworks.append("SpecKit")
    if has_planning:
        frameworks.append("CGSD")

    result = {
        "frameworks": frameworks,
        "has_validation_config": has_claude_validation,
        "primary": None,
        "commands": [],
        "context_message": None,
    }

    if not frameworks:
        result["primary"] = None
        result["context_message"] = None
    elif len(frameworks) == 1:
        result["primary"] = frameworks[0]
    else:
        # Both present, prefer SpecKit as primary
        result["primary"] = "SpecKit"

    # Set available commands based on framework
    if "SpecKit" in frameworks:
        result["commands"].extend(
            [
                "/speckit.specify",
                "/speckit.plan",
                "/speckit.tasks",
                "/speckit.implement",
                "/speckit.analyze",
                "/speckit.clarify",
            ]
        )

    if "CGSD" in frameworks:
        result["commands"].extend(
            [
                "gsd:init",
                "gsd:plan",
                "gsd:verify",
            ]
        )

    # Build context message if framework detected
    if result["primary"]:
        msg_parts = [f"Framework detected: {result['primary']}"]

        if result["commands"]:
            msg_parts.append(f"Available commands: {', '.join(result['commands'][:4])}")

        if not has_claude_validation:
            msg_parts.append("Note: Missing .claude/validation/config.json for /spec-pipeline")

        result["context_message"] = " | ".join(msg_parts)

    return result


def main():
    """Main hook function - called as UserPromptSubmit hook."""
    with contextlib.suppress(Exception):
        json.load(sys.stdin)  # Consume stdin for hook protocol

    # Get current working directory
    cwd = os.getcwd()

    # Detect framework
    detection = detect_framework(cwd)

    # Build output
    output = {
        "cwd": cwd,
        "detection": detection,
    }

    # If framework detected, provide context injection
    if detection["context_message"]:
        output["hookSpecificOutput"] = {
            "hookEventName": "UserPromptSubmit",
            "message": detection["context_message"],
        }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
