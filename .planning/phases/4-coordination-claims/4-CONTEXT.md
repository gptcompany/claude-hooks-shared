# Phase 4: Coordination & Claims - Context

**Gathered:** 2026-01-20
**Status:** Ready for research

<vision>
## How This Should Work

Multi-agent work distribution with **rock-solid collision avoidance**. When multiple Task agents run in parallel, the system automatically detects potential conflicts and coordinates transparently — no explicit user action needed.

**Core model:**
- **Task-level dispatch**: Agents get assigned tasks automatically
- **File-level locking**: Collision prevention at the file level — agents never work on the same file simultaneously
- Different agents CAN work on the same task if they're touching different files

**When an agent finishes:**
- Broadcast completion — announce release so waiting agents know immediately (more robust than polling/timeout)

**When an agent gets stuck:**
- Timeout & reassign — after idle threshold, mark claims as stealable so another agent can take over

</vision>

<essential>
## What Must Be Nailed

All three equally important, no compromises:

- **Zero file conflicts** — Never lose work due to race conditions. Rock solid.
- **Smart dispatch** — Agents get the right work assigned automatically.
- **Full visibility** — Clear view of who's working on what:
  - Dashboard/status command to see current state
  - Real-time logging of claim/release events
  - Summary stats when work completes

</essential>

<specifics>
## Specific Ideas

- Coordination should be **intelligent and automatic** — activates when needed, stays quiet otherwise
- **Don't modify existing GSD commands** — coordination lives in hooks, not command rewrites. Only custom commands can be modified.
- Hooks live in the **shared hooks folder** (consistent with claude-hooks-shared structure)
- Relationship with Phase 5 (Swarm) unclear — boundary to be clarified during implementation

</specifics>

<notes>
## Additional Context

This phase provides the foundation for multi-agent work. Key insight: file-level granularity is critical — task-level locking would be too coarse and block legitimate parallel work.

The system should "just work" without requiring users to think about coordination explicitly. It's infrastructure that prevents problems, not a feature users interact with directly.

</notes>

---

*Phase: 04-coordination-claims*
*Context gathered: 2026-01-20*
