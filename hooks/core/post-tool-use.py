#!/usr/bin/env python3
"""
PostToolUse Hook: Log tool usage and detect error patterns (Multi-Project Template)

This hook is called after each Claude Code tool execution. It:
1. Calculates tool duration from PreToolUse start time
2. Logs tool usage to QuestDB (time-series)
3. Detects error patterns (tdd_block, timeout, etc.)
4. Records events for recurring pattern detection

Database:
    QuestDB via ILP protocol (replaces PostgreSQL)
    - claude_tool_usage table: Individual tool invocations
    - claude_events table: Error and block tracking

ENV VARIABLES:
    QUESTDB_HOST: QuestDB host (default: localhost)
    QUESTDB_ILP_PORT: QuestDB ILP port (default: 9009)

Returns:
    JSON response: {"success": True} to confirm logging completed
"""

import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add shared scripts to path for QuestDB import
scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

try:
    from questdb_metrics import QuestDBMetrics
except ImportError:
    # Fail gracefully if QuestDB not available
    QuestDBMetrics = None

# Read hook input with error handling
try:
    hook_data = json.loads(sys.stdin.read())
except json.JSONDecodeError as e:
    print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
    sys.exit(0)  # Exit 0 to not block Claude

session_id = hook_data.get("session_id")
tool_name = hook_data.get("tool_name")
success = hook_data.get("success", True)
error = hook_data.get("error")

# Validate required fields
if not session_id or not tool_name:
    print(json.dumps({"success": False, "error": "Missing session_id or tool_name"}))
    sys.exit(0)

# Sanitize file path components
safe_session = re.sub(r"[^a-zA-Z0-9\-_]", "_", str(session_id))
safe_tool = re.sub(r"[^a-zA-Z0-9\-_]", "_", str(tool_name))

# Calculate duration using cross-platform temp directory
temp_dir = tempfile.gettempdir()
start_file = Path(temp_dir) / f"claude_tool_start_{safe_session}_{safe_tool}"

duration_ms = 0
if start_file.exists():
    try:
        start_time = datetime.fromisoformat(start_file.read_text().strip())
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        start_file.unlink()  # Cleanup
    except (ValueError, OSError):
        pass

# Log to QuestDB
if QuestDBMetrics is not None:
    try:
        writer = QuestDBMetrics()

        # Log tool usage
        writer.log_tool_use(
            session_id=session_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=success,
            error=error[:200] if error else None,
        )

        # Detect and log error events
        if not success and error:
            error_lower = error.lower()
            if "tdd" in error_lower or "test" in error_lower:
                event_type = "tdd_block"
            elif "timeout" in error_lower:
                event_type = "timeout"
            elif "hook" in error_lower or "blocked" in error_lower:
                event_type = "hook_block"
            else:
                event_type = "error"

            writer.log_event(
                session_id=session_id, event_type=event_type, tool_name=tool_name, error_message=error[:200]
            )

        print(json.dumps({"success": True}))

    except Exception as e:
        # Don't fail hook on QuestDB errors
        print(json.dumps({"success": False, "error": str(e)}))
else:
    # QuestDB not available, but don't block
    print(json.dumps({"success": True, "note": "QuestDB not configured"}))

sys.exit(0)
