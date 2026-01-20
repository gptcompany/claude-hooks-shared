# Phase 4: Coordination & Claims - Research

**Researched:** 2026-01-20
**Domain:** Multi-agent coordination via claude-flow MCP APIs
**Confidence:** HIGH

<research_summary>
## Summary

Researched claude-flow's coordination and claims APIs for implementing multi-agent work distribution with file-level locking. The claude-flow MCP server already provides a comprehensive claims system with conflict detection, steal/handoff protocols, and broadcast notifications.

Key finding: **Don't hand-roll coordination logic**. The claude-flow claims API already provides:
- Claim/release lifecycle with conflict detection
- Mark-stealable for timeout/reassign scenarios
- Broadcast notifications via `hooks_notify`
- Load balancing via `claims_load` and `claims_rebalance`
- Visual board view via `claims_board`

**Primary recommendation:** Wrap claude-flow claims APIs in hooks that intercept Write/Edit/Task tools. Use file paths as issueIds for file-level locking. Leverage existing `hooks_notify` for broadcast on release.

</research_summary>

<standard_stack>
## Standard Stack

### Core (already available via claude-flow MCP)
| API | Purpose | Why Use It |
|-----|---------|------------|
| `claims_claim` | Claim a file/task for exclusive work | Conflict detection built-in |
| `claims_release` | Release claim when done | Returns previousClaim for audit |
| `claims_mark-stealable` | Mark stuck work as stealable | Supports timeout/reassign pattern |
| `claims_steal` | Take over stealable work | Clean handoff semantics |
| `claims_status` | Update progress on claim | Visibility into agent progress |
| `claims_board` | Visual board of all claims | Dashboard view |
| `claims_list` | List claims with filters | Query active/stealable/completed |
| `claims_load` | Get agent workload | Smart dispatch decisions |
| `claims_rebalance` | Suggest/apply rebalancing | Automatic distribution |
| `hooks_notify` | Broadcast message to agents | Release notifications |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `coordination_topology` | Configure swarm structure | Phase 5, not needed here |
| `coordination_sync` | State synchronization | Complex multi-node scenarios |
| `hive-mind_broadcast` | Swarm-wide messages | Phase 5, heavier than hooks_notify |

### Existing Codebase Patterns
| File | Pattern | Reuse For |
|------|---------|-----------|
| `hooks/core/mcp_client.py` | CLI/file-based claude-flow access | Backup if MCP unavailable |
| `hooks/intelligence/trajectory_tracker.py` | PreToolUse/PostToolUse/Stop hooks | Hook structure template |
| `~/.claude/settings.json` | Hook registration | Add coordination hooks |

</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Hook Structure
```
hooks/coordination/
├── __init__.py
├── file_claim.py          # PreToolUse(Write|Edit) - claim file
├── file_release.py        # PostToolUse(Write|Edit) - release file
├── task_claim.py          # PreToolUse(Task) - claim task
├── task_release.py        # SubagentStop - release task
├── stuck_detector.py      # Stop - mark stuck claims stealable
└── claims_dashboard.py    # Utility script for /claims-board command
```

### Pattern 1: File-Level Claim on Edit
**What:** Claim file before editing, release after
**When to use:** Always for Write/Edit/MultiEdit tools
**Example:**
```python
# PreToolUse hook for Write|Edit|MultiEdit
def on_pre_edit(hook_input):
    file_path = hook_input["tool_input"].get("file_path")
    if not file_path:
        return {}

    # Claim the file
    result = mcp_claim(
        issueId=f"file:{file_path}",
        claimant=f"agent:{session_id}:editor"
    )

    if not result["success"]:
        # File already claimed - block the edit
        return {
            "decision": "block",
            "reason": f"File claimed by {result['existingClaim']['claimant']}"
        }

    return {}  # Allow edit to proceed
```

### Pattern 2: Broadcast on Release
**What:** Notify waiting agents when file becomes available
**When to use:** PostToolUse for Write/Edit/MultiEdit
**Example:**
```python
# PostToolUse hook
def on_post_edit(hook_input):
    file_path = hook_input["tool_input"].get("file_path")

    # Release the claim
    mcp_release(
        issueId=f"file:{file_path}",
        claimant=f"agent:{session_id}:editor"
    )

    # Broadcast availability
    mcp_notify(
        message=f"File released: {file_path}",
        target="all",
        data={"file": file_path, "event": "release"}
    )

    return {}
```

### Pattern 3: Timeout & Steal
**What:** Mark claims stealable after idle threshold
**When to use:** Stop hook or periodic check
**Example:**
```python
# Stop hook - mark any active claims as stealable
def on_stop(hook_input):
    claims = mcp_claims_list(claimant=f"agent:{session_id}:*")

    for claim in claims:
        if claim["status"] == "active":
            mcp_mark_stealable(
                issueId=claim["issueId"],
                reason="blocked-timeout",
                context="Agent session ended with active claim"
            )

    return {}
```

### Anti-Patterns to Avoid
- **File-based locks**: Don't use `.lock` files - race conditions, stale locks
- **Task-level only locking**: Too coarse - blocks legitimate parallel file work
- **Polling for availability**: Use broadcast notifications instead
- **Custom claim storage**: Use claude-flow's built-in claims system

</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File locking | fcntl/flock, .lock files | `claims_claim` with file: prefix | Cross-process, visible, timeout support |
| Conflict detection | Custom lock checks | `claims_claim` returns existingClaim | Atomic, race-free |
| Waiting for release | Polling, sleep loops | `hooks_notify` broadcast | Event-driven, immediate |
| Stuck detection | Custom timers | `claims_mark-stealable` + timeout | Built-in steal protocol |
| Work distribution | Custom queue | `claims_load` + `claims_rebalance` | Load-aware, adaptive |
| Dashboard | Custom file/db | `claims_board` | Real-time, visual |

**Key insight:** claude-flow already implements distributed coordination primitives. The claims system is designed for exactly this use case. Rolling custom locks will have race conditions and lack visibility.

</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Forgetting to Release Claims
**What goes wrong:** Files stay claimed after agent finishes, blocking future work
**Why it happens:** Error paths don't release, or Stop hook not registered
**How to avoid:**
- Register Stop hook to release all active claims
- Use try/finally pattern in claim/release
- Mark claims stealable on Stop as fallback
**Warning signs:** `claims_board` shows stale "active" claims with old timestamps

### Pitfall 2: Claim ID Mismatch
**What goes wrong:** Release fails because issueId doesn't match exactly
**Why it happens:** Path normalization differs (relative vs absolute, trailing slash)
**How to avoid:**
- Always use `os.path.abspath()` for file paths
- Use consistent prefix (`file:` for files, `task:` for tasks)
- Store claimed IDs for later release
**Warning signs:** "Issue not found" errors on release

### Pitfall 3: Claimant ID Mismatch
**What goes wrong:** Can't release because claimant doesn't match original
**Why it happens:** Session ID changes, or format differs
**How to avoid:**
- Store claimant ID at claim time
- Use consistent format: `agent:{session_id}:{type}`
- Pass same claimant to release
**Warning signs:** "Not authorized to release" errors

### Pitfall 4: Blocking on Claimed Files
**What goes wrong:** Agent hangs waiting for file, user sees no progress
**Why it happens:** No timeout, no feedback to user
**How to avoid:**
- Return "block" decision with clear reason
- Include current owner in message
- Offer alternatives (different file, wait, steal)
**Warning signs:** Agent appears stuck with no output

### Pitfall 5: Missing SubagentStop Hook
**What goes wrong:** Task agent's claims not released when it finishes
**Why it happens:** SubagentStop hook not registered for coordination
**How to avoid:**
- Register SubagentStop hook for task_release.py
- Query claims by agent ID on SubagentStop
- Release all claims for that agent
**Warning signs:** Orphaned claims from completed subagents

</common_pitfalls>

<code_examples>
## Code Examples

### Verified: Claim a File
```python
# Source: claude-flow MCP API testing
result = mcp__claude_flow__claims_claim(
    issueId="file:/media/sam/1TB/claude-hooks-shared/hooks/test.py",
    claimant="agent:research-1:research",
    context="Testing file-level claim"
)
# Result:
# {
#   "success": true,
#   "claim": {
#     "issueId": "file:/media/sam/...",
#     "claimant": {"type": "agent", "agentId": "research-1", "agentType": "research"},
#     "status": "active",
#     "progress": 0
#   }
# }
```

### Verified: Conflict Detection
```python
# Second claim on same file fails
result = mcp__claude_flow__claims_claim(
    issueId="file:/media/sam/1TB/claude-hooks-shared/hooks/test.py",
    claimant="agent:other-1:coder"
)
# Result:
# {
#   "success": false,
#   "error": "Issue already claimed by agent:research-1:research",
#   "existingClaim": {...}
# }
```

### Verified: Broadcast Notification
```python
# Notify all agents of file release
result = mcp__claude_flow__hooks_notify(
    message="File released: /path/to/file.py",
    target="all",
    priority="normal",
    data={"file": "/path/to/file.py", "event": "release"}
)
# Result:
# {
#   "delivered": true,
#   "recipients": ["coder", "architect", "tester", "reviewer"]
# }
```

### Hook Registration Pattern (from settings.json)
```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit|MultiEdit",
      "hooks": [
        {
          "type": "command",
          "command": "/media/sam/1TB/claude-hooks-shared/hooks/coordination/file_claim.py",
          "timeout": 5
        }
      ]
    }
  ],
  "PostToolUse": [
    {
      "matcher": "Write|Edit|MultiEdit",
      "hooks": [
        {
          "type": "command",
          "command": "/media/sam/1TB/claude-hooks-shared/hooks/coordination/file_release.py",
          "timeout": 5
        }
      ]
    }
  ],
  "SubagentStop": [
    {
      "matcher": "",
      "hooks": [
        {
          "type": "command",
          "command": "/media/sam/1TB/claude-hooks-shared/hooks/coordination/task_release.py",
          "timeout": 5
        }
      ]
    }
  ]
}
```

</code_examples>

<sota_updates>
## State of the Art (2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| File-based locks (.lock) | claude-flow claims API | 2025 | Cross-process visibility, timeout support |
| Custom coordination | claude-flow MCP primitives | 2025 | Standardized, observable, recoverable |
| Polling for availability | hooks_notify broadcast | 2025 | Event-driven, immediate |

**New tools/patterns available:**
- `claims_rebalance`: Automatic load distribution across agents
- `claims_board`: Visual dashboard of all claims
- `hooks_notify`: Cross-agent notification system

**Deprecated/outdated:**
- `coordination_orchestrate`: Heavy, use claims + hooks_notify for Phase 4
- Custom lock files: Race conditions, no visibility

</sota_updates>

<open_questions>
## Open Questions

1. **Session ID persistence across restarts**
   - What we know: Hooks can use environment or file-based session tracking
   - What's unclear: Best way to maintain consistent agent identity
   - Recommendation: Use `trajectory_tracker.py` pattern - generate UUID per session, store in file

2. **Timeout duration for stuck detection**
   - What we know: `claims_mark-stealable` exists with reason "blocked-timeout"
   - What's unclear: Optimal timeout threshold
   - Recommendation: Start with 60s for file claims, 300s for task claims, make configurable

3. **Integration with Phase 5 Swarm**
   - What we know: Phase 4 provides coordination primitives
   - What's unclear: Which features belong in Phase 4 vs Phase 5
   - Recommendation: Phase 4 = hooks + claims API. Phase 5 = hive-mind, consensus, swarm lifecycle

</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- claude-flow MCP API testing - claims_*, hooks_notify verified working
- `/media/sam/1TB/claude-hooks-shared/hooks/core/mcp_client.py` - existing pattern
- `/media/sam/1TB/claude-hooks-shared/hooks/intelligence/trajectory_tracker.py` - hook structure
- `~/.claude/settings.json` - hook registration pattern

### Secondary (MEDIUM confidence)
- claude-flow documentation patterns inferred from API responses

### Tertiary (LOW confidence - needs validation)
- None - all findings verified via actual API calls

</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: claude-flow MCP claims and coordination APIs
- Ecosystem: Existing hook infrastructure in claude-hooks-shared
- Patterns: File-level locking, broadcast notifications, timeout/steal
- Pitfalls: Release failures, ID mismatches, missing hooks

**Confidence breakdown:**
- Standard stack: HIGH - verified via MCP API calls
- Architecture: HIGH - based on existing hook patterns
- Pitfalls: HIGH - derived from API behavior analysis
- Code examples: HIGH - actual tested calls

**Research date:** 2026-01-20
**Valid until:** 2026-02-20 (30 days - claude-flow API stable)

</metadata>

---

*Phase: 04-coordination-claims*
*Research completed: 2026-01-20*
*Ready for planning: yes*
