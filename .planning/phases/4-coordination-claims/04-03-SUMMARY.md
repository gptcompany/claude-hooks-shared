# Plan 04-03 Summary: Stuck Detection and Claims Dashboard

**Completed:** 2026-01-20
**Status:** Done

## What Was Built

### 1. stuck_detector.py (Stop Hook)

**File:** `/media/sam/1TB/claude-hooks-shared/hooks/coordination/stuck_detector.py`

A Stop hook that runs when a session ends. It ensures any claims held by this session are marked as stealable so other agents can take over the work.

**Features:**
- Reads session_id from session state file (`/tmp/claude-metrics/session_state.json`)
- Queries claims store for active claims belonging to this session
- Marks each active claim as stealable with reason "blocked-timeout"
- Clears session state file after processing
- Handles errors gracefully - session end never fails
- Supports `--dry-run` flag for testing

**Implementation details:**
- Uses direct file access to `~/.claude-flow/claims/claims.json` (same store as MCP server)
- Claimant pattern: `agent:{session_id}:*`
- Logs all actions to `/tmp/claude-metrics/coordination.log`

### 2. claims_dashboard.py (Utility Script)

**File:** `/media/sam/1TB/claude-hooks-shared/hooks/coordination/claims_dashboard.py`

A standalone utility (NOT a hook) that displays the current claims board in a formatted table with boxes/borders.

**Features:**
- Reads directly from claims store file for real-time accuracy
- Displays ACTIVE and STEALABLE sections with claim details
- Shows summary stats (active, stealable, completed counts)
- Supports `--json` flag for raw JSON output
- Supports `--watch` flag for auto-refresh (default 5 seconds)
- Supports `--interval N` for custom refresh interval
- Supports `--width N` for custom display width

**Usage:**
```bash
python3 claims_dashboard.py              # Formatted output
python3 claims_dashboard.py --json       # JSON output
python3 claims_dashboard.py --watch      # Watch mode (5s refresh)
python3 claims_dashboard.py --watch -i 10  # 10s refresh
```

**Sample output:**
```
════════════════════════════════════════════════════════════
                      CLAIMS DASHBOARD
════════════════════════════════════════════════════════════

ACTIVE (0):
  (none)

STEALABLE (0):
  (none)

Summary: 0 active, 0 stealable, 0 completed
════════════════════════════════════════════════════════════
```

## Architecture Decisions

### Direct File Access Pattern

Both scripts use direct file access to `~/.claude-flow/claims/claims.json` instead of CLI commands. This follows the established pattern in `hooks/core/mcp_client.py` and ensures:

1. **Consistency**: Same store as MCP server reads/writes
2. **Speed**: No subprocess overhead
3. **Reliability**: Works even if claude-flow CLI unavailable

### Claims Store Format

```json
{
  "claims": {
    "file:/path/to/file.py": {
      "claimant": "agent:session123:editor",
      "status": "active",
      "claimedAt": "2026-01-20T12:00:00Z",
      "progress": 0
    }
  },
  "stealable": {
    "file:/path/to/other.py": {
      "claimant": "agent:old-session:editor",
      "status": "stealable",
      "stealReason": "blocked-timeout",
      "markedStealableAt": "2026-01-20T12:05:00Z",
      "availableFor": "any"
    }
  },
  "contests": {}
}
```

## Verification

- [x] stuck_detector.py is executable
- [x] claims_dashboard.py is executable
- [x] stuck_detector marks claims as stealable on Stop
- [x] claims_dashboard shows formatted output
- [x] claims_dashboard --json returns valid JSON
- [x] Both scripts handle errors gracefully

## Files Modified

- `hooks/coordination/__init__.py` - Updated to include new modules
- `hooks/coordination/stuck_detector.py` - Created (new)
- `hooks/coordination/claims_dashboard.py` - Created (new)

## Integration Notes

### Hook Registration (for settings.json)

The stuck_detector.py should be registered as a Stop hook:

```json
{
  "Stop": [
    {
      "matcher": "",
      "hooks": [
        {
          "type": "command",
          "command": "/media/sam/1TB/claude-hooks-shared/hooks/coordination/stuck_detector.py",
          "timeout": 5
        }
      ]
    }
  ]
}
```

### Session State File

For stuck_detector to work, the session must write its identity to `/tmp/claude-metrics/session_state.json`:

```json
{
  "session_id": "unique-session-identifier"
}
```

This should be done by the session_start hook or task_claim.py when claiming tasks.
