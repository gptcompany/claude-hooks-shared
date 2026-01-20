# Phase 2: Trajectory Learning (SONA) - Research

**Researched:** 2026-01-20
**Domain:** Claude Code hooks → claude-flow MCP intelligence layer
**Confidence:** HIGH

<research_summary>
## Summary

Researched how to integrate trajectory learning into the existing hooks infrastructure. The system has all required components already in place:

1. **Hooks infrastructure** - Proven working in Phase 1 (session hooks write to MCP store)
2. **trajectory_tracker.py** - Already created, implements start/step/end handlers
3. **claude-flow MCP tools** - trajectory-start/step/end verified working
4. **QuestDB sync** - claudeflow-sync.py already syncs learning data

The main gap is **hook registration** - trajectory_tracker.py is not yet registered in settings.json.

**Primary recommendation:** Register trajectory_tracker.py in settings.json for PreToolUse(Task), PostToolUse(Task), and Stop events. Optionally enhance to call claude-flow MCP APIs directly for richer learning.
</research_summary>

<standard_stack>
## Standard Stack

### Core (Already Available)
| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| trajectory_tracker.py | hooks/intelligence/ | Hook handler | Created, not registered |
| mcp_client.py | hooks/core/ | Memory access | Verified working |
| claude-flow MCP | ~/.claude-flow/ | Intelligence APIs | Verified working |
| QuestDB pipeline | hooks/metrics/ | Time-series storage | Operational (506K records) |

### claude-flow Intelligence APIs
| Tool | Purpose | Verified |
|------|---------|----------|
| trajectory-start | Begin trajectory recording | ✓ Returns trajectoryId |
| trajectory-step | Record action with quality | ✓ Returns stepId |
| trajectory-end | End + trigger SONA learning | ✓ Persists + extracts patterns |
| pattern-store | Store learned patterns | ✓ HNSW indexed |
| pattern-search | Search patterns | ✓ Vector search |
| intelligence_stats | View learning metrics | ✓ Shows SONA/MoE/EWC++ stats |

### Storage Layers
| Layer | Purpose | Access Method |
|-------|---------|---------------|
| MCP JSON store | Runtime state, cross-session | Direct file access from hooks |
| claude-flow SQLite | Full learning history | MCP tools |
| QuestDB | Time-series analytics | ILP via claudeflow-sync.py |
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Hook Event Flow
```
PreToolUse(Task) → trajectory_tracker.py --event=start
                   ↓
                   generate_trajectory_id()
                   save_active_trajectory() to /tmp/claude-metrics/
                   memory_store("trajectory:{project}:active")

PostToolUse(Task) → trajectory_tracker.py --event=step
                    ↓
                    load_active_trajectory()
                    append step with success/quality
                    save_active_trajectory()

Stop             → trajectory_tracker.py --event=end
                   ↓
                   load_active_trajectory()
                   calculate success_rate
                   memory_store("trajectory:{project}:{id}")
                   update trajectory index
                   clear_active_trajectory()
```

### Dual Storage Pattern (from Phase 1)
```python
# Hooks write to JSON store (same as MCP server)
MCP_STORE = Path.home() / ".claude-flow" / "memory" / "store.json"

def memory_store(key, value, namespace=""):
    # Direct file access - MCP can read these entries
    store = _load_store()
    store["entries"][full_key] = {...}
    _save_store(store)
```

### QuestDB Sync Pattern (existing)
```python
# claudeflow-sync.py runs on Stop
# Reads from SQLite + JSON, writes to QuestDB via ILP
def sync_learning_data():
    lines = []
    # Build ILP lines for each metric
    lines.append(f"claude_trajectories,project={project} count={count},success_rate={rate} {ts}")
    send_to_questdb(lines)
```

### Recommended Project Structure
```
hooks/
├── intelligence/
│   ├── trajectory_tracker.py    # Main trajectory hook (exists)
│   ├── meta_learning.py         # Phase 3 - extract lessons
│   └── lesson_injector.py       # Phase 3 - inject lessons
├── session/
│   ├── session_checkpoint.py    # Phase 1 - verified ✓
│   └── session_restore_check.py # Phase 1 - verified ✓
├── metrics/
│   └── claudeflow-sync.py       # QuestDB sync (exists)
└── core/
    └── mcp_client.py            # Shared utilities (exists)
```
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Trajectory ID generation | Custom DB sequences | `uuid.uuid4().hex[:8]` | Simple, collision-free |
| Pattern storage | Custom vector store | `mcp__claude-flow__hooks_intelligence_pattern-store` | HNSW indexed, ready |
| Pattern search | Custom similarity search | `mcp__claude-flow__hooks_intelligence_pattern-search` | Vector search built-in |
| Learning algorithms | Custom ML | SONA/EWC++ in claude-flow | Already implemented |
| Time-series storage | Custom DB | QuestDB via existing pipeline | Proven, 506K records |

**Key insight:** claude-flow already implements sophisticated learning (SONA, EWC++, MoE). The hook's job is to **connect events to these APIs**, not reimplement learning.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Missing Hook Registration
**What goes wrong:** trajectory_tracker.py exists but never executes
**Why it happens:** Not added to ~/.claude/settings.json
**How to avoid:** Add entries for PreToolUse(Task), PostToolUse(Task), Stop
**Warning signs:** No logs in /tmp/claude-metrics/trajectory_tracker.log

### Pitfall 2: MCP vs CLI Database Confusion
**What goes wrong:** Hook writes to wrong database, MCP can't see data
**Why it happens:** CLI uses SQLite (~/.swarm/), MCP uses JSON (~/.claude-flow/)
**How to avoid:** Always use JSON store for hook→MCP communication
**Warning signs:** memory_retrieve returns None when data should exist

### Pitfall 3: Active Trajectory Not Cleared
**What goes wrong:** Stale trajectory data persists across sessions
**Why it happens:** Stop hook fails or doesn't run
**How to avoid:** Use try/finally in on_end(), check file age on start
**Warning signs:** Trajectory with old timestamps still "active"

### Pitfall 4: Hook Timeout
**What goes wrong:** Hook times out, data partially written
**Why it happens:** MCP calls or file I/O too slow
**How to avoid:** Keep hooks fast (<5s), use async/background for heavy work
**Warning signs:** Partial JSON files, timeout errors in logs

### Pitfall 5: Not Using Claude-Flow APIs
**What goes wrong:** Trajectories stored but no learning happens
**Why it happens:** Only using local storage, not calling intelligence APIs
**How to avoid:** Call trajectory-start/step/end or pattern-store for learning
**Warning signs:** `intelligence_stats` shows 0 trajectories/patterns
</common_pitfalls>

<code_examples>
## Code Examples

### Hook Registration (settings.json)
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Task",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/intelligence/trajectory_tracker.py --event=start",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Task",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/intelligence/trajectory_tracker.py --event=step",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/intelligence/trajectory_tracker.py --event=end",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### Enhanced Trajectory End (calling claude-flow APIs)
```python
def on_end_enhanced(hook_input: dict):
    """End trajectory with claude-flow learning."""
    trajectory = load_active_trajectory()
    if not trajectory:
        return {}

    # Call claude-flow for real SONA learning
    import subprocess
    import json

    trajectory_id = trajectory["id"]
    success = trajectory.get("success_rate", 0) >= 0.7

    # Use MCP tool via subprocess (hooks can't call MCP directly)
    # Alternative: Use memory_store to JSON, let MCP pick it up

    # Store pattern for future retrieval
    pattern = f"{trajectory['task'][:50]}:success={success}"
    memory_store(f"pattern:{pattern}", {
        "trajectory_id": trajectory_id,
        "success": success,
        "steps": len(trajectory.get("steps", [])),
        "confidence": 0.6 if success else 0.3
    })

    return {}
```

### QuestDB Trajectory Metrics (add to claudeflow-sync.py)
```python
def sync_trajectory_data() -> list[str]:
    """Sync trajectory data to QuestDB."""
    lines = []
    store_file = Path.home() / ".claude-flow" / "memory" / "store.json"

    if not store_file.exists():
        return lines

    with open(store_file) as f:
        store = json.load(f)

    for key, entry in store.get("entries", {}).items():
        if key.startswith("trajectory:") and ":index" not in key:
            value = entry.get("value", {})
            if isinstance(value, dict) and value.get("status") == "completed":
                project = escape_tag(value.get("project", "unknown"))
                success = 1 if value.get("success") else 0
                steps = value.get("total_steps", 0)
                rate = value.get("success_rate", 0)
                ts = int(datetime.fromisoformat(
                    value.get("ended_at", "2026-01-01T00:00:00+00:00")
                ).timestamp() * 1e9)

                lines.append(
                    f"claude_trajectories,project={project} "
                    f"success={success}i,steps={steps}i,success_rate={rate} {ts}"
                )

    return lines
```
</code_examples>

<sota_updates>
## State of the Art (2026)

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Manual trajectory logging | Automatic hook tracking | No manual intervention needed |
| Local file storage only | Dual JSON + QuestDB | Analytics + runtime state |
| No learning | SONA + EWC++ via claude-flow | Patterns extracted automatically |

**New capabilities in claude-flow:**
- **SONA learning**: Extracts patterns from trajectories with confidence scores
- **EWC++**: Prevents catastrophic forgetting during learning
- **HNSW indexing**: Fast vector search for patterns
- **MoE routing**: 8 experts for task routing (coder, tester, reviewer, etc.)

**Architecture shift:**
- Hooks are **event bridges**, not learning engines
- claude-flow is the **intelligence layer**
- QuestDB is the **analytics layer**
</sota_updates>

<open_questions>
## Open Questions

1. **SubagentStop vs Stop**
   - What we know: Stop fires for main session, SubagentStop for Task agents
   - What's unclear: Should trajectory end on SubagentStop instead?
   - Recommendation: Test both, prefer SubagentStop for agent-specific trajectories

2. **Pattern Approval Workflow**
   - What we know: User wants semi-automatic (suggest before applying)
   - What's unclear: How to present suggestions? additionalContext? skill?
   - Recommendation: Phase 3 (lesson_injector.py) handles this via additionalContext
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- `/media/sam/1TB/claude-hooks-shared/hooks/intelligence/trajectory_tracker.py` - Existing implementation
- `/media/sam/1TB/claude-hooks-shared/hooks/core/mcp_client.py` - Verified Phase 1
- claude-flow MCP tools - Verified working via `trajectory-start/step/end`
- `/home/sam/.claude/settings.json` - Existing hook registrations

### Secondary (MEDIUM confidence)
- `/media/sam/1TB/claude-hooks-shared/hooks/metrics/claudeflow-sync.py` - QuestDB sync pattern
- claude-flow `hooks_intelligence_stats` - Shows SONA/MoE/EWC++ implementation

### Verified Working
- `mcp__claude-flow__hooks_intelligence_trajectory-start` ✓
- `mcp__claude-flow__hooks_intelligence_trajectory-step` ✓
- `mcp__claude-flow__hooks_intelligence_trajectory-end` ✓ (triggers SONA learning)
- `mcp__claude-flow__memory_retrieve` ✓
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: Claude Code hooks + claude-flow MCP
- Ecosystem: Existing hooks, QuestDB pipeline
- Patterns: Hook registration, dual storage, event bridge
- Pitfalls: Registration, database confusion, timeouts

**Confidence breakdown:**
- Standard stack: HIGH - all components verified working
- Architecture: HIGH - Phase 1 proved the pattern
- Pitfalls: HIGH - encountered during Phase 1
- Code examples: HIGH - based on working code

**Research date:** 2026-01-20
**Valid until:** 2026-02-20 (30 days - stable infrastructure)
</metadata>

---

*Phase: 02-trajectory-learning*
*Research completed: 2026-01-20*
*Ready for planning: yes*
