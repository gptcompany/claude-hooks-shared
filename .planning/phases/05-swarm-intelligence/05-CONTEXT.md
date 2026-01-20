# Phase 5: Swarm Intelligence - Context

**Gathered:** 2026-01-20
**Status:** Ready for research

<vision>
## How This Should Work

Hybrid approach: Claude detects parallelizable work (task complexity detection) and auto-initializes swarm with notification — no asking, just "swarm initialized for this task" then it happens.

The swarm powers everything parallelizable:
- GSD phase execution (priority #1) — when /gsd:execute-phase runs multiple plans
- Codebase-wide changes (refactoring, migrations)
- Research & exploration (multiple agents exploring)
- Ad-hoc parallel tasks ("do X and Y in parallel")

Two coordination systems working in parallel:
- **File claims (Phase 4)** — fine-grained file-level locking
- **Swarm consensus** — high-level task coordination

Simple /swarm command with minimal feedback — KISS. Just confirmation it worked, then get out of the way.

</vision>

<essential>
## What Must Be Nailed

- **Coordination** — Agents don't step on each other. File claims for files, swarm consensus for tasks. This is THE priority.
- **GSD integration** — /gsd:execute-phase becomes swarm-powered. This is the primary use case.
- **Completion model** — All workers must report success. Any failure triggers auto-retry (sensible default, not configurable).

</essential>

<specifics>
## Specific Ideas

- Auto-init swarm when task complexity detected, notify but don't ask
- Workers share knowledge minimally — only when necessary for conflict resolution
- Simple retry on failure (1-2 retries before surfacing as blocked)
- Two-layer coordination: claims for files, swarm for tasks (parallel systems, not replacement)
- Minimal /swarm command output — KISS principle

</specifics>

<notes>
## Additional Context

Phase 4 (Coordination & Claims) is verified and working — swarm should build on top of it, not replace it. The claims system handles file-level locking; swarm handles task-level orchestration.

User wants "full swarm experience" but prioritizes GSD phase execution as the first use case to nail. The swarm should feel automatic and invisible when it's working — just faster execution.

Failure handling: retry automatically with sensible defaults. Don't make the user configure retry counts.

</notes>

---

*Phase: 05-swarm-intelligence*
*Context gathered: 2026-01-20*
