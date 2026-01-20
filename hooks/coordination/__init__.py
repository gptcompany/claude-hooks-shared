"""Coordination hooks for multi-agent work distribution.

This module provides hooks for claiming and releasing files/tasks
to prevent conflicts when multiple agents work in parallel.

Hooks:
- task_claim.py: PreToolUse hook for Task tool - claims task for visibility
- task_release.py: SubagentStop hook - releases task claims on completion
- file_claim.py: PreToolUse hook for Write/Edit - claims file (blocks on conflict)
- file_release.py: PostToolUse hook for Write/Edit - releases file claim
- stuck_detector.py: Stop hook - marks active claims as stealable on session end

Utilities:
- claims_dashboard.py: Standalone script to display claims board
"""

__all__ = [
    "task_claim",
    "task_release",
    "file_claim",
    "file_release",
    "stuck_detector",
    "claims_dashboard",
]
