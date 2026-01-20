#!/usr/bin/env python3
"""Helper per chiamare claude-flow CLI da hooks.

Questo modulo fornisce un'interfaccia semplice per chiamare i comandi
claude-flow CLI da hook Python.

Comandi supportati:
- memory store/retrieve/search/list
- session save/restore/list
- hooks intelligence trajectory-start/step/end
- hooks intelligence pattern-store/search
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

# Setup logging
LOG_DIR = Path(os.environ.get("METRICS_DIR", "/tmp/claude-metrics"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "mcp_client.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _run_claude_flow(args: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Run claude-flow CLI command.

    Returns:
        tuple: (success, output)
    """
    try:
        cmd = ["npx", "-y", "claude-flow@latest"] + args
        logger.debug(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home()),
        )

        output = result.stdout.strip() or result.stderr.strip()
        success = result.returncode == 0

        if not success:
            logger.warning(f"Command failed: {output}")
        else:
            logger.debug(f"Output: {output[:200]}...")

        return success, output

    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {args}")
        return False, "timeout"
    except Exception as e:
        logger.error(f"Command error: {e}")
        return False, str(e)


def memory_store(key: str, value: Any, namespace: str = "") -> dict:
    """Store value in claude-flow memory.

    Writes directly to MCP store file (~/.claude-flow/memory/store.json)
    to ensure consistency with MCP server.
    """
    full_key = f"{namespace}:{key}" if namespace else key

    # Use direct file access (same store as MCP server)
    return _direct_memory_store(full_key, value)


def memory_retrieve(key: str, namespace: str = "") -> Any:
    """Retrieve value from claude-flow memory.

    Reads directly from MCP store file (~/.claude-flow/memory/store.json)
    to ensure consistency with MCP server.
    """
    full_key = f"{namespace}:{key}" if namespace else key

    # Use direct file access (same store as MCP server)
    return _direct_memory_retrieve(full_key)


def memory_search(query: str, top_k: int = 5) -> list[dict]:
    """Search claude-flow memory.

    Uses: claude-flow memory search -q "query"
    """
    success, output = _run_claude_flow(
        ["memory", "search", "-q", query, "-n", str(top_k)]
    )

    if not success:
        return []

    # Parse results - this is best effort
    results = []
    # Output format varies, return raw for now
    return [{"raw": output}] if output else []


def memory_list() -> list[str]:
    """List memory keys.

    Uses: claude-flow memory list
    """
    success, output = _run_claude_flow(["memory", "list"])

    if not success:
        return _fallback_memory_list()

    # Parse table output to extract keys
    keys = []
    for line in output.split("\n"):
        if "|" in line and "Key" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) > 1 and parts[1]:
                keys.append(parts[1])

    return keys


def session_save(name: str, include_memory: bool = True) -> dict:
    """Save current session.

    Uses: claude-flow session save -n "name"
    """
    success, output = _run_claude_flow(["session", "save", "-n", name])

    return {"success": success, "output": output}


def session_restore(name: str) -> dict:
    """Restore a saved session.

    Uses: claude-flow session restore "name"
    """
    success, output = _run_claude_flow(["session", "restore", name])

    return {"success": success, "output": output}


def session_list() -> list[dict]:
    """List saved sessions.

    Uses: claude-flow session list
    """
    success, output = _run_claude_flow(["session", "list"])

    if not success:
        return []

    # Parse output - return raw for now
    return [{"raw": output}]


# Direct MCP storage access (same format as MCP server uses)
# This ensures hooks write to the same store that MCP reads from

MCP_STORE_FILE = Path.home() / ".claude-flow" / "memory" / "store.json"


def _ensure_mcp_store():
    """Ensure MCP store file exists with correct structure."""
    MCP_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not MCP_STORE_FILE.exists():
        with open(MCP_STORE_FILE, "w") as f:
            json.dump({"entries": {}}, f)


def _load_mcp_store() -> dict:
    """Load MCP store."""
    _ensure_mcp_store()
    try:
        with open(MCP_STORE_FILE) as f:
            data = json.load(f)
        if "entries" not in data:
            data = {"entries": {}}
        return data
    except Exception as e:
        logger.error(f"Load MCP store error: {e}")
        return {"entries": {}}


def _save_mcp_store(data: dict):
    """Save MCP store."""
    _ensure_mcp_store()
    with open(MCP_STORE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _direct_memory_store(key: str, value: Any) -> dict:
    """Store directly to MCP memory file (same format as MCP server)."""
    try:
        from datetime import datetime, timezone

        store = _load_mcp_store()
        now = datetime.now(timezone.utc).isoformat()

        # Handle both dict and string values (MCP stores some as JSON strings)
        stored_value = value

        store["entries"][key] = {
            "key": key,
            "value": stored_value,
            "metadata": {},
            "storedAt": now,
            "accessCount": 0,
            "lastAccessed": now,
        }

        _save_mcp_store(store)
        logger.info(f"Stored to MCP store: {key}")
        return {"success": True, "direct": True}
    except Exception as e:
        logger.error(f"Direct store error: {e}")
        return {"success": False, "error": str(e)}


def _direct_memory_retrieve(key: str) -> Any:
    """Retrieve directly from MCP memory file."""
    try:
        store = _load_mcp_store()

        if key in store["entries"]:
            entry = store["entries"][key]
            # Update access count
            entry["accessCount"] = entry.get("accessCount", 0) + 1
            entry["lastAccessed"] = get_timestamp()
            _save_mcp_store(store)

            logger.info(f"Retrieved from MCP store: {key}")
            value = entry.get("value")

            # Handle JSON string values
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return value
        return None
    except Exception as e:
        logger.error(f"Direct retrieve error: {e}")
        return None


def _direct_memory_list() -> list[str]:
    """List keys from MCP memory file."""
    try:
        store = _load_mcp_store()
        return list(store["entries"].keys())
    except Exception:
        return []


# Alias for backwards compatibility
_fallback_memory_store = _direct_memory_store
_fallback_memory_retrieve = _direct_memory_retrieve
_fallback_memory_list = _direct_memory_list


# Utility functions


def get_project_name() -> str:
    """Get current project name from environment or cwd."""
    if project := os.environ.get("CLAUDE_PROJECT"):
        return project

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except Exception:
        pass

    return Path.cwd().name


def get_timestamp() -> str:
    """Get ISO timestamp."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# Intelligence/Learning functions (use hooks subcommand)


def trajectory_start(task: str, agent: str = "main") -> str | None:
    """Start a new trajectory.

    Uses: claude-flow hooks intelligence trajectory-start
    """
    success, output = _run_claude_flow(
        ["hooks", "intelligence", "trajectory-start", "--task", task, "--agent", agent]
    )

    if success and "id" in output.lower():
        # Try to extract trajectory ID from output
        for line in output.split("\n"):
            if "id" in line.lower():
                parts = line.split(":")
                if len(parts) > 1:
                    return parts[-1].strip()

    return None


def trajectory_step(trajectory_id: str, action: str, quality: float = 1.0) -> dict:
    """Record a trajectory step."""
    success, output = _run_claude_flow(
        [
            "hooks",
            "intelligence",
            "trajectory-step",
            "--id",
            trajectory_id,
            "--action",
            action,
            "--quality",
            str(quality),
        ]
    )

    return {"success": success, "output": output}


def trajectory_end(trajectory_id: str, success_flag: bool) -> dict:
    """End a trajectory."""
    success, output = _run_claude_flow(
        [
            "hooks",
            "intelligence",
            "trajectory-end",
            "--id",
            trajectory_id,
            "--success" if success_flag else "--fail",
        ]
    )

    return {"success": success, "output": output}


def pattern_store(
    pattern: str, pattern_type: str, confidence: float, metadata: dict | None = None
) -> dict:
    """Store a learned pattern."""
    args = [
        "hooks",
        "intelligence",
        "pattern-store",
        "--pattern",
        pattern,
        "--type",
        pattern_type,
        "--confidence",
        str(confidence),
    ]

    if metadata:
        args.extend(["--metadata", json.dumps(metadata)])

    success, output = _run_claude_flow(args)
    return {"success": success, "output": output}


def pattern_search(
    query: str, top_k: int = 3, min_confidence: float = 0.7
) -> list[dict]:
    """Search learned patterns."""
    success, output = _run_claude_flow(
        [
            "hooks",
            "intelligence",
            "pattern-search",
            "-q",
            query,
            "-n",
            str(top_k),
            "--min-confidence",
            str(min_confidence),
        ]
    )

    if not success:
        return []

    return [{"raw": output}] if output else []


def intelligence_learn(consolidate: bool = True) -> dict:
    """Trigger learning consolidation."""
    args = ["hooks", "intelligence", "learn"]
    if consolidate:
        args.append("--consolidate")

    success, output = _run_claude_flow(args)
    return {"success": success, "output": output}


if __name__ == "__main__":
    # Test the client
    print("Testing claude-flow CLI client...")

    # Test memory store
    print("\n1. Testing memory store...")
    result = memory_store("test:client", {"test": True, "timestamp": get_timestamp()})
    print(f"   Result: {result}")

    # Test memory retrieve
    print("\n2. Testing memory retrieve...")
    value = memory_retrieve("test:client")
    print(f"   Value: {value}")

    # Test memory list
    print("\n3. Testing memory list...")
    keys = memory_list()
    print(f"   Keys: {keys}")

    # Test session list
    print("\n4. Testing session list...")
    sessions = session_list()
    print(f"   Sessions: {sessions}")

    print("\nDone!")
