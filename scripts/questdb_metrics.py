#!/usr/bin/env python3
"""
QuestDB Metrics Writer - Direct ILP protocol

Replaces PostgreSQL session_manager for tool logging.
Writes directly to QuestDB via InfluxDB Line Protocol (ILP).

Performance: ~5ms per write (socket reuse) vs ~150ms (PostgreSQL connection)

USAGE:
    writer = QuestDBMetrics()
    writer.log_tool_use("session_123", "Edit", {"file": "main.py"})

ENV VARIABLES:
    QUESTDB_HOST: QuestDB host (default: localhost)
    QUESTDB_ILP_PORT: QuestDB ILP port (default: 9009)
"""

import os
import socket
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

# Import project auto-detect
sys.path.insert(0, str(Path(__file__).parent))
try:
    from project_utils import get_project_name
except ImportError:

    def get_project_name():
        return os.getenv("CLAUDE_PROJECT_NAME", "unknown")


# Socket singleton for connection reuse
_socket = None
_socket_lock = threading.Lock()

# Config
QUESTDB_HOST = os.environ.get("QUESTDB_HOST", "localhost")
QUESTDB_ILP_PORT = int(os.environ.get("QUESTDB_ILP_PORT", "9009"))


def _get_socket() -> Optional[socket.socket]:
    """Get or create reusable socket connection."""
    global _socket
    if _socket is None:
        with _socket_lock:
            if _socket is None:
                try:
                    _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    _socket.connect((QUESTDB_HOST, QUESTDB_ILP_PORT))
                    _socket.settimeout(2.0)  # 2s timeout
                except (socket.error, OSError):
                    _socket = None
    return _socket


def _reset_socket():
    """Reset socket on error."""
    global _socket
    with _socket_lock:
        if _socket:
            try:
                _socket.close()
            except Exception:
                pass
            _socket = None


def _escape_tag(value: str) -> str:
    """Escape tag value for ILP."""
    return value.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_field_str(value: str) -> str:
    """Escape string field value for ILP."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _to_ilp(table: str, tags: dict, fields: dict, timestamp_ns: int) -> str:
    """Convert to ILP line."""
    # Tags
    tag_parts = []
    for k, v in tags.items():
        if v:
            tag_parts.append(f"{k}={_escape_tag(str(v))}")
    tag_str = ",".join(tag_parts)

    # Fields
    field_parts = []
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, bool):
            field_parts.append(f"{k}={'t' if v else 'f'}")
        elif isinstance(v, int):
            field_parts.append(f"{k}={v}i")
        elif isinstance(v, float):
            field_parts.append(f"{k}={v}")
        elif isinstance(v, str):
            field_parts.append(f'{k}="{_escape_field_str(v)}"')

    if not field_parts:
        return ""

    field_str = ",".join(field_parts)

    if tag_str:
        return f"{table},{tag_str} {field_str} {timestamp_ns}"
    return f"{table} {field_str} {timestamp_ns}"


class QuestDBMetrics:
    """QuestDB metrics writer using ILP protocol."""

    def __init__(self, project_name: str = None):
        """Initialize with optional project name override."""
        self.project_name = project_name or get_project_name()

    def _send(self, line: str) -> bool:
        """Send ILP line to QuestDB."""
        if not line:
            return False

        sock = _get_socket()
        if not sock:
            return False

        try:
            sock.sendall((line + "\n").encode())
            return True
        except (socket.error, OSError):
            _reset_socket()
            return False

    def log_tool_use(
        self,
        session_id: str,
        tool_name: str,
        tool_params: dict = None,
        duration_ms: int = 0,
        success: bool = True,
        error: str = None,
    ) -> bool:
        """
        Log tool usage to QuestDB.

        Table: claude_tool_usage
        Tags: project, session_id, tool_name
        Fields: duration_ms, success, error, params_summary
        """
        tags = {
            "project": self.project_name,
            "session_id": session_id[:50] if session_id else "unknown",
            "tool_name": tool_name or "unknown",
        }

        # Summarize params (keep it short for QuestDB)
        params_summary = ""
        if tool_params:
            if "file_path" in tool_params:
                params_summary = Path(tool_params["file_path"]).name[:50]
            elif "command" in tool_params:
                cmd = tool_params["command"]
                params_summary = cmd[:50] if len(cmd) <= 50 else cmd[:47] + "..."
            elif "pattern" in tool_params:
                params_summary = tool_params["pattern"][:50]

        fields = {
            "duration_ms": duration_ms,
            "success": success,
        }
        if error:
            fields["error"] = error[:200]
        if params_summary:
            fields["params"] = params_summary

        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = _to_ilp("claude_tool_usage", tags, fields, timestamp_ns)

        return self._send(line)

    def log_event(
        self,
        session_id: str,
        event_type: str,
        tool_name: str = None,
        error_message: str = None,
        severity: str = "medium",
    ) -> bool:
        """
        Log event (error, block, etc) to QuestDB.

        Table: claude_events
        """
        tags = {
            "project": self.project_name,
            "session_id": session_id[:50] if session_id else "unknown",
            "event_type": event_type,
            "severity": severity,
        }
        if tool_name:
            tags["tool_name"] = tool_name

        fields = {"count": 1}
        if error_message:
            fields["error"] = error_message[:200]

        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = _to_ilp("claude_events", tags, fields, timestamp_ns)

        return self._send(line)

    def log_session_metric(
        self,
        session_id: str,
        tokens_input: int = 0,
        tokens_output: int = 0,
        tokens_cache: int = 0,
        cost_usd: float = 0.0,
        lines_added: int = 0,
        lines_removed: int = 0,
        git_branch: str = None,
        task_type: str = None,
    ) -> bool:
        """
        Log session metrics snapshot to QuestDB.

        Table: claude_sessions

        Cost Attribution fields:
        - git_branch: Feature branch for cost tracking
        - task_type: Category (feature, bugfix, refactor, etc.)
        """
        tags = {
            "project": self.project_name,
            "session_id": session_id[:50] if session_id else "unknown",
        }

        # Cost Attribution tags
        if git_branch:
            tags["git_branch"] = git_branch[:50]
        if task_type:
            tags["task_type"] = task_type[:20]

        fields = {
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tokens_cache": tokens_cache,
            "cost_usd": cost_usd,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
        }

        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = _to_ilp("claude_sessions", tags, fields, timestamp_ns)

        return self._send(line)

    def log_agent(
        self,
        session_id: str,
        agent_type: str,
        duration_ms: int = 0,
        success: bool = True,
        tokens_used: int = 0,
        tool_calls: int = 0,
        prompt_length: int = 0,
        result_length: int = 0,
        error: str = None,
        parent_agent: str = None,
    ) -> bool:
        """
        Log agent spawn and execution to QuestDB.

        Table: claude_agents
        """
        tags = {
            "project": self.project_name,
            "session_id": session_id[:50] if session_id else "unknown",
            "agent_type": agent_type or "unknown",
        }
        if parent_agent:
            tags["parent_agent"] = parent_agent

        fields = {
            "duration_ms": duration_ms,
            "success": success,
            "tokens_used": tokens_used,
            "tool_calls": tool_calls,
            "prompt_length": prompt_length,
            "result_length": result_length,
        }
        if error:
            fields["error"] = error[:200]

        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = _to_ilp("claude_agents", tags, fields, timestamp_ns)

        return self._send(line)

    def log_hook(
        self,
        hook_type: str,
        hook_name: str,
        duration_ms: int = 0,
        success: bool = True,
        blocked: bool = False,
        modified: bool = False,
        tool_matcher: str = None,
        error: str = None,
    ) -> bool:
        """
        Log hook execution to QuestDB.

        Table: claude_hooks
        """
        tags = {
            "project": self.project_name,
            "hook_type": hook_type,
            "hook_name": hook_name,
        }
        if tool_matcher:
            tags["tool_matcher"] = tool_matcher

        fields = {
            "duration_ms": duration_ms,
            "success": success,
            "blocked": blocked,
            "modified": modified,
        }
        if error:
            fields["error"] = error[:200]

        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = _to_ilp("claude_hooks", tags, fields, timestamp_ns)

        return self._send(line)

    def log_task(
        self,
        session_id: str,
        task_content: str,
        task_status: str,
        duration_min: float = 0.0,
        tool_calls: int = 0,
        tokens_used: int = 0,
    ) -> bool:
        """
        Log task lifecycle to QuestDB.

        Table: claude_tasks
        """
        tags = {
            "project": self.project_name,
            "session_id": session_id[:50] if session_id else "unknown",
            "task_status": task_status,
        }

        fields = {
            "task_content": task_content[:200] if task_content else "",
            "duration_min": duration_min,
            "tool_calls": tool_calls,
            "tokens_used": tokens_used,
        }

        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = _to_ilp("claude_tasks", tags, fields, timestamp_ns)

        return self._send(line)

    def log_context(
        self, session_id: str, context_used: int, context_max: int = 200000, message_count: int = 0
    ) -> bool:
        """
        Log context window utilization to QuestDB.

        Table: claude_context
        """
        tags = {
            "project": self.project_name,
            "session_id": session_id[:50] if session_id else "unknown",
        }

        utilization_pct = (context_used / context_max * 100) if context_max > 0 else 0

        fields = {
            "context_used": context_used,
            "context_max": context_max,
            "utilization_pct": utilization_pct,
            "message_count": message_count,
        }

        timestamp_ns = int(datetime.now().timestamp() * 1e9)
        line = _to_ilp("claude_context", tags, fields, timestamp_ns)

        return self._send(line)

    def close(self):
        """Close socket connection (optional, for cleanup)."""
        _reset_socket()


# Convenience function for backward compatibility
def get_metrics_writer(project_name: str = None) -> QuestDBMetrics:
    """Get a QuestDB metrics writer instance."""
    return QuestDBMetrics(project_name)
