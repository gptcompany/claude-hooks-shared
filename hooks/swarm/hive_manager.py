#!/usr/bin/env python3
"""Hive Manager Hook - Swarm lifecycle for parallel task execution.

This module provides functions for managing claude-flow hive-mind swarms.
It enables automatic swarm initialization, worker spawning, task distribution,
consensus proposals, and coordinated shutdown.

Usage:
    # As module
    from hooks.swarm.hive_manager import init_swarm, spawn_workers, get_status
    result = init_swarm(topology="hierarchical-mesh")

    # As CLI
    python3 hive_manager.py --action init --topology hierarchical-mesh
    python3 hive_manager.py --action status
    python3 hive_manager.py --action spawn --count 3
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Logging
LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "swarm.log"


def log(msg: str):
    """Log message to file."""
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(LOG_FILE, "a") as f:
            f.write(f"{timestamp} - [hive_manager] {msg}\n")
    except Exception:
        pass


def _run_hive_cmd(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Run claude-flow hive-mind command.

    Args:
        args: List of arguments for hive-mind subcommand
        timeout: Command timeout in seconds

    Returns:
        tuple: (success, output_or_error)
    """
    cmd = ["npx", "-y", "claude-flow@latest", "hive-mind"] + args

    log(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home()),
        )

        output = result.stdout.strip() or result.stderr.strip()
        success = result.returncode == 0

        log(f"Result: success={success}, output={output[:200] if output else 'empty'}")
        return success, output

    except subprocess.TimeoutExpired:
        log(f"Command timed out after {timeout}s")
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        log(f"Command error: {e}")
        return False, str(e)


def init_swarm(topology: str = "hierarchical-mesh") -> dict:
    """Initialize hive-mind swarm with specified topology.

    Args:
        topology: Swarm topology - one of: hierarchical-mesh, mesh, star, ring

    Returns:
        dict: {"success": bool, "output": str, "hive_id": str|None}
    """
    log(f"Initializing swarm with topology: {topology}")

    success, output = _run_hive_cmd(["init", "-t", topology])

    # Try to extract hive_id from output
    hive_id = None
    if success and output:
        # Look for patterns like "Hive ID: abc123" or "hive_id": "abc123"
        match = re.search(r"(?:hive[_\s]?id|Hive ID)[:\s]+([a-zA-Z0-9_-]+)", output, re.I)
        if match:
            hive_id = match.group(1)

    return {
        "success": success,
        "output": output,
        "hive_id": hive_id,
    }


def spawn_workers(count: int = 3) -> dict:
    """Spawn workers into the hive.

    Args:
        count: Number of workers to spawn (default: 3)

    Returns:
        dict: {"success": bool, "output": str, "workers": list}
    """
    log(f"Spawning {count} workers")

    success, output = _run_hive_cmd(["spawn", "-n", str(count)])

    # Try to extract worker IDs from output
    workers = []
    if success and output:
        # Look for patterns like "Worker: abc123" or "worker_id": "abc123"
        workers = re.findall(r"(?:worker[_\s]?id|Worker)[:\s]+([a-zA-Z0-9_-]+)", output, re.I)

    return {
        "success": success,
        "output": output,
        "workers": workers,
    }


def submit_task(description: str, priority: str = "normal") -> dict:
    """Submit a task to the hive for parallel execution.

    Args:
        description: Task description
        priority: Task priority - one of: low, normal, high

    Returns:
        dict: {"success": bool, "output": str, "task_id": str|None}
    """
    log(f"Submitting task: {description[:50]}...")

    args = ["task", "-d", description]
    if priority != "normal":
        args.extend(["--priority", priority])

    success, output = _run_hive_cmd(args)

    # Try to extract task_id from output
    task_id = None
    if success and output:
        match = re.search(r"(?:task[_\s]?id|Task ID)[:\s]+([a-zA-Z0-9_-]+)", output, re.I)
        if match:
            task_id = match.group(1)

    return {
        "success": success,
        "output": output,
        "task_id": task_id,
    }


def get_status(verbose: bool = True) -> dict:
    """Get current hive status.

    Args:
        verbose: Include detailed status information

    Returns:
        dict: {"success": bool, "output": str, "workers_active": int}
    """
    log("Getting hive status")

    args = ["status"]
    if verbose:
        args.append("--verbose")

    success, output = _run_hive_cmd(args)

    # Try to extract worker count from output
    workers_active = 0
    if output:
        # Look for patterns like "Workers: 3" or "workers_active": 3
        match = re.search(r"(?:workers?[_\s]?active|Workers?)[:\s]+(\d+)", output, re.I)
        if match:
            workers_active = int(match.group(1))

    return {
        "success": success,
        "output": output,
        "workers_active": workers_active,
    }


def propose_consensus(topic: str, options: list[str]) -> dict:
    """Propose a consensus vote to the hive.

    Args:
        topic: Topic for consensus vote
        options: List of options to vote on

    Returns:
        dict: {"success": bool, "output": str, "proposal_id": str|None}
    """
    log(f"Proposing consensus: {topic}")

    options_json = json.dumps(options)
    success, output = _run_hive_cmd(
        [
            "consensus",
            "propose",
            "--topic",
            topic,
            "--options",
            options_json,
        ],
        timeout=60,
    )

    # Try to extract proposal_id from output
    proposal_id = None
    if success and output:
        match = re.search(r"(?:proposal[_\s]?id|Proposal ID)[:\s]+([a-zA-Z0-9_-]+)", output, re.I)
        if match:
            proposal_id = match.group(1)

    return {
        "success": success,
        "output": output,
        "proposal_id": proposal_id,
    }


def broadcast_message(message: str, target: str = "all") -> dict:
    """Broadcast a message to workers in the hive.

    Args:
        message: Message to broadcast
        target: Target workers - "all" or specific worker ID

    Returns:
        dict: {"success": bool, "output": str}
    """
    log(f"Broadcasting message to {target}: {message[:50]}...")

    args = ["broadcast", "-m", message]
    if target != "all":
        args.extend(["--target", target])

    success, output = _run_hive_cmd(args)

    return {
        "success": success,
        "output": output,
    }


def shutdown_swarm(graceful: bool = True) -> dict:
    """Shutdown the hive-mind swarm.

    Args:
        graceful: Perform graceful shutdown (default: True)

    Returns:
        dict: {"success": bool, "output": str}
    """
    log(f"Shutting down swarm (graceful={graceful})")

    args = ["shutdown"]
    if not graceful:
        args.append("--force")

    success, output = _run_hive_cmd(args)

    return {
        "success": success,
        "output": output,
    }


def main():
    """CLI entry point for testing and manual operations."""
    parser = argparse.ArgumentParser(
        description="Hive Manager - Swarm lifecycle management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Actions:
  init       Initialize a new swarm
  spawn      Spawn workers into the swarm
  task       Submit a task to the swarm
  status     Get swarm status
  consensus  Propose a consensus vote
  broadcast  Broadcast a message to workers
  shutdown   Shutdown the swarm

Examples:
  %(prog)s --action init --topology hierarchical-mesh
  %(prog)s --action status
  %(prog)s --action spawn --count 3
  %(prog)s --action task --description "Implement feature X"
  %(prog)s --action shutdown
        """,
    )

    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "init",
            "spawn",
            "task",
            "status",
            "consensus",
            "broadcast",
            "shutdown",
        ],
        help="Action to perform",
    )
    parser.add_argument(
        "--topology",
        default="hierarchical-mesh",
        choices=["hierarchical-mesh", "mesh", "star", "ring"],
        help="Swarm topology (for init action)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of workers to spawn (for spawn action)",
    )
    parser.add_argument(
        "--description",
        help="Task description (for task action)",
    )
    parser.add_argument(
        "--priority",
        default="normal",
        choices=["low", "normal", "high"],
        help="Task priority (for task action)",
    )
    parser.add_argument(
        "--topic",
        help="Consensus topic (for consensus action)",
    )
    parser.add_argument(
        "--options",
        help="Consensus options as JSON array (for consensus action)",
    )
    parser.add_argument(
        "--message",
        help="Message to broadcast (for broadcast action)",
    )
    parser.add_argument(
        "--target",
        default="all",
        help="Broadcast target (for broadcast action)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="Verbose output (for status action)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force shutdown (for shutdown action)",
    )

    args = parser.parse_args()

    # Execute action
    if args.action == "init":
        result = init_swarm(topology=args.topology)
    elif args.action == "spawn":
        result = spawn_workers(count=args.count)
    elif args.action == "task":
        if not args.description:
            parser.error("--description required for task action")
        result = submit_task(description=args.description, priority=args.priority)
    elif args.action == "status":
        result = get_status(verbose=args.verbose)
    elif args.action == "consensus":
        if not args.topic or not args.options:
            parser.error("--topic and --options required for consensus action")
        try:
            options = json.loads(args.options)
        except json.JSONDecodeError:
            parser.error("--options must be valid JSON array")
        result = propose_consensus(topic=args.topic, options=options)
    elif args.action == "broadcast":
        if not args.message:
            parser.error("--message required for broadcast action")
        result = broadcast_message(message=args.message, target=args.target)
    elif args.action == "shutdown":
        result = shutdown_swarm(graceful=not args.force)
    else:
        parser.error(f"Unknown action: {args.action}")

    # Output result as JSON
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
