# Claude-Flow Systematic Integration

## What This Is

A hooks-based automation system that integrates claude-flow MCP tools non-discretionally into Claude Code sessions. Currently claude-flow infrastructure exists (SQLite, QuestDB, memory store) but is 95% unused. This project makes claude-flow learning, session recovery, and coordination automatic via Python hooks.

## Core Value

**Automatic learning from every session** - patterns, lessons, and trajectories are captured and reinjected without explicit user invocation, enabling cross-session intelligence.

## Requirements

### Validated

- ✓ MCP client helper for claude-flow calls — v0.1 (mcp_client.py created)

### Active

- [ ] Session checkpoint on Stop hook (auto-save sessions)
- [ ] Session restore check on UserPromptSubmit (crash recovery)
- [ ] Trajectory tracking on Task Pre/Post/Stop (SONA learning)
- [ ] Meta-learning extraction on Stop (lesson capture)
- [ ] Lesson injection on UserPromptSubmit (pattern reuse)
- [ ] Coordination hooks for multi-agent orchestration
- [ ] Swarm/hive-mind management hooks
- [ ] Claims system for work distribution
- [ ] /swarm skill command for manual control
- [ ] settings.json hook registration

### Out of Scope

- GUI/dashboard for hook management — use Grafana existing dashboards
- New MCP server development — leverage existing claude-flow
- Hooks for tools other than Task — focus on agent coordination first

## Context

**Current State:**
- claude-hooks-shared has existing hooks structure: `/hooks/{core,intelligence,session,metrics,...}`
- claude-flow MCP provides 100+ tools but only ~5% are actively used
- QuestDB metrics pipeline exists and works
- Memory entries: 10 (should be 100s)
- Trajectories recorded: 0
- Patterns learned: 0

**Gap Analysis:**
| Feature | Status | Impact |
|---------|--------|--------|
| memory_store/retrieve | PARTIAL | No cross-session learning |
| session_save/restore | NOT USED | No crash recovery |
| trajectory_* | NOT USED | No SONA learning |
| pattern_store/search | NOT USED | No lesson persistence |
| coordination_orchestrate | NOT USED | Manual orchestration |
| hive-mind_* | NOT USED | No swarm intelligence |
| claims_* | NOT USED | No load balancing |

**Root Cause:** Claude-flow is called only when explicitly requested. Solution: automatic hooks.

## Constraints

- **Hook timeout**: Max 10 seconds per hook execution
- **MCP access**: Hooks use subprocess (npx claude-flow) not direct MCP
- **Fallback**: Memory operations have local file fallback
- **Non-blocking**: Hooks must not break Claude sessions on failure

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python hooks calling claude-flow CLI | Hooks can't access MCP directly | — Pending |
| Local file fallback for memory | Resilience if claude-flow unavailable | — Pending |
| Dual-write to claude-flow + QuestDB | Runtime state + metrics persistence | — Pending |
| Focus on Task tool hooks | Highest value for agent coordination | — Pending |

---
*Last updated: 2026-01-20 after initialization*
