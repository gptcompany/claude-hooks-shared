# Claude-Flow Systematic Integration

## What This Is

A hooks-based automation system that integrates claude-flow MCP tools non-discretionally into Claude Code sessions. The system captures patterns, lessons, and trajectories automatically, enabling cross-session intelligence and multi-agent coordination.

## Core Value

**Automatic learning from every session** - patterns, lessons, and trajectories are captured and reinjected without explicit user invocation.

## Current State (v1.0 Shipped)

**Tech Stack:** Python hooks, claude-flow CLI, JSON store, QuestDB metrics
**LOC:** ~13,600 Python lines across ~1,145 files
**Tests:** 56+ tests passing

**Capabilities:**
- Session checkpoint/restore for crash recovery
- Trajectory tracking for SONA learning
- Meta-learning pattern extraction (rework, errors, quality)
- Lesson injection by confidence level
- File-level coordination with claims system
- Swarm intelligence with hive-mind

## Requirements

### Validated

- ✓ Session checkpoint on Stop hook (auto-save sessions) — v1.0
- ✓ Session restore check on UserPromptSubmit (crash recovery) — v1.0
- ✓ Trajectory tracking on Task Pre/Post/Stop (SONA learning) — v1.0
- ✓ Meta-learning extraction on Stop (lesson capture) — v1.0
- ✓ Lesson injection on UserPromptSubmit (pattern reuse) — v1.0
- ✓ Coordination hooks for multi-agent orchestration — v1.0
- ✓ Claims system for work distribution — v1.0
- ✓ /swarm skill command for manual control — v1.0
- ✓ settings.json hook registration — v1.0
- ✓ MCP client helper for claude-flow calls — v0.1 (mcp_client.py)

### Active

(None - v1.0 complete, awaiting v1.1 planning)

### Out of Scope

- GUI/dashboard for hook management — use Grafana existing dashboards
- New MCP server development — leverage existing claude-flow
- Hooks for tools other than Task — focus on agent coordination first

## Context

**v1.0 Achievements:**
- 5 phases completed in single day intensive
- All hooks registered and tested
- MCP and CLI interoperability confirmed
- Non-blocking design ensures stability

**Architecture:**
- Hooks read/write to `~/.claude-flow/memory/store.json` (shared with MCP)
- Logging to `/tmp/claude-metrics/*.log`
- State files in `/tmp/claude-metrics/*.json`
- Claims system in `~/.claude-flow/claims/claims.json`

## Constraints

- **Hook timeout**: Max 10 seconds per hook execution
- **MCP access**: Hooks use subprocess (npx claude-flow) not direct MCP
- **Fallback**: Memory operations have local file fallback
- **Non-blocking**: Hooks must not break Claude sessions on failure

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python hooks calling claude-flow CLI | Hooks can't access MCP directly | ✓ Good - works reliably |
| Local file fallback for memory | Resilience if claude-flow unavailable | ✓ Good - never blocks |
| Dual-write to claude-flow + QuestDB | Runtime state + metrics persistence | ✓ Good - queryable |
| Focus on Task tool hooks | Highest value for agent coordination | ✓ Good - covers main use case |
| JSON file store (not SQLite) | MCP and CLI share same store | ✓ Good - interoperable |
| Non-blocking design | Session stability critical | ✓ Good - failures logged only |
| KISS principle | Avoid over-engineering | ✓ Good - maintainable |

---
*Last updated: 2026-01-20 after v1.0 milestone*
