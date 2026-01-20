"""Swarm hooks for multi-agent parallel task execution.

This module provides hooks for managing swarm lifecycle using claude-flow hive-mind.
It enables automatic swarm initialization, worker spawning, task distribution,
and consensus-based coordination.

Main module:
- hive_manager: Core swarm lifecycle functions (init, spawn, task, status, shutdown)
"""

from . import hive_manager

__all__ = [
    "hive_manager",
]
