# Phase 2: Trajectory Learning (SONA) - Context

**Gathered:** 2026-01-20
**Status:** Ready for implementation

<vision>
## How This Should Work

Trajectory learning is a comprehensive system that tracks everything agents do and uses that data three ways:

1. **Flight recorder** - Every agent action gets logged silently for debugging. When something goes wrong, you can see exactly what happened.

2. **Pattern discovery** - Successful trajectories get analyzed to find common patterns that work. These patterns are stored and can be reused.

3. **Auto-improvement** - Agents gradually get better based on past successes/failures. The system learns what works.

The system should be mostly invisible during normal operation - it just records. But when you need it (debugging, analyzing, improving), all the data is there.

</vision>

<essential>
## What Must Be Nailed

- **Dual scope** - Both project-specific patterns AND cross-project global patterns, with appropriate weighting
- **Triple visibility** - Grafana dashboards for trends, CLI for quick lookups, detailed logs for deep debugging
- **Full integration** - Not standalone - integrates with session recovery, lesson learning, and coordination as those phases complete
- **Dual storage** - MCP (claude-flow) for runtime state, QuestDB for analytics and historical queries - kept in sync
- **Semi-automatic learning** - Records and learns automatically, but suggests patterns for approval before applying them

</essential>

<specifics>
## Specific Ideas

- Uses existing `trajectory_tracker.py` (already created in hooks/intelligence/)
- Hooks into PreToolUse(Task), PostToolUse(Task), and Stop events
- Calls claude-flow MCP tools: `trajectory-start`, `trajectory-step`, `trajectory-end`
- Syncs to QuestDB via existing metrics pipeline
- Patterns suggested via `additionalContext` injection (like session recovery does)

</specifics>

<notes>
## Additional Context

claude-flow intelligence tools are verified working:
- trajectory-start: Creates trajectory ID
- trajectory-step: Records actions with quality scores
- trajectory-end: Triggers SONA learning, stores patterns

The hooks system is the bridge between Claude Code events and claude-flow MCP. Phase 1 proved this architecture works (session hooks write to MCP store, MCP reads them).

</notes>

---

*Phase: 02-trajectory-learning*
*Context gathered: 2026-01-20*
