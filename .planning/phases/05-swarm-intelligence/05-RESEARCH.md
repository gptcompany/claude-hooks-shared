# Phase 5: Swarm Intelligence - Research

**Researched:** 2026-01-20
**Domain:** Multi-agent coordination with claude-flow hive-mind
**Confidence:** HIGH

<research_summary>
## Summary

Researched multi-agent swarm coordination patterns for implementing hive-mind in Claude Code hooks. The standard approach uses the **orchestrator-worker pattern** (central coordinator dispatches to parallel workers) combined with **hierarchical file locking** (existing Phase 4 claims system).

Key finding: claude-flow v3.0 provides comprehensive hive-mind primitives (init, spawn, consensus, broadcast, memory) that should be leveraged rather than hand-rolled. The existing Phase 4 claims system handles file-level coordination; swarm should handle task-level orchestration on top of it.

**Primary recommendation:** Use claude-flow hive-mind commands (`hive-mind init`, `hive-mind spawn`, `hive-mind task`) via CLI subprocess calls, following the established pattern in `mcp_client.py`. Implement continuous dispatch scheduling (no wave barriers) for optimal parallelism.

</research_summary>

<standard_stack>
## Standard Stack

### Core (claude-flow v3.0.0-alpha.136)
| Command | Purpose | Why Standard |
|---------|---------|--------------|
| `hive-mind init` | Initialize hive with topology | Entry point for swarm coordination |
| `hive-mind spawn` | Spawn workers into hive | Creates coordinated worker agents |
| `hive-mind task` | Submit tasks to hive | Task distribution primitive |
| `hive-mind status` | Monitor hive state | Visibility into swarm health |
| `hive-mind consensus` | Propose/vote on decisions | Coordination for conflicting changes |
| `hive-mind broadcast` | Message all workers | Cross-agent communication |
| `hive-mind memory` | Shared memory access | State sharing between workers |
| `hive-mind shutdown` | Graceful termination | Clean swarm lifecycle end |

### Supporting (already in codebase)
| Component | Purpose | Location |
|-----------|---------|----------|
| `mcp_client.py` | CLI wrapper for claude-flow | `hooks/core/mcp_client.py` |
| `file_claim.py` | File-level locking | `hooks/coordination/file_claim.py` |
| `task_claim.py` | Task visibility tracking | `hooks/coordination/task_claim.py` |
| `stuck_detector.py` | Orphan claim cleanup | `hooks/coordination/stuck_detector.py` |

### Topologies Available
| Topology | When to Use | Tradeoff |
|----------|-------------|----------|
| `hierarchical-mesh` | GSD phase execution (default) | Best for structured work, clear roles |
| `mesh` | Ad-hoc parallel tasks | More flexible, less structured |
| `star` | Single coordinator pattern | Simple but coordinator is bottleneck |
| `ring` | Pipeline processing | Sequential dependencies |

**CLI Usage:**
```bash
# Initialize swarm with hierarchical mesh
npx -y claude-flow@latest hive-mind init -t hierarchical-mesh

# Spawn 3 workers into hive
npx -y claude-flow@latest hive-mind spawn -n 3

# Submit task to hive
npx -y claude-flow@latest hive-mind task -d "Implement feature X"

# Check status
npx -y claude-flow@latest hive-mind status --verbose

# Graceful shutdown
npx -y claude-flow@latest hive-mind shutdown
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
```
hooks/
├── swarm/
│   ├── __init__.py
│   ├── hive_manager.py      # Main swarm lifecycle hook
│   ├── task_dispatcher.py   # Task complexity detection + dispatch
│   └── worker_monitor.py    # Worker health + completion tracking
├── coordination/            # Existing Phase 4 (keep unchanged)
│   ├── file_claim.py
│   ├── task_claim.py
│   └── stuck_detector.py
skills/
└── swarm.md                 # /swarm skill command
```

### Pattern 1: Two-Layer Coordination
**What:** File claims (Phase 4) + Swarm consensus (Phase 5) operate in parallel
**When to use:** Always — this is the core architecture
**How it works:**
```
                    ┌──────────────────┐
                    │  Swarm Layer     │ ← Task-level coordination
                    │  (hive-mind)     │   (consensus, dispatch)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Claims Layer    │ ← File-level coordination
                    │  (Phase 4)       │   (locks, conflicts)
                    └──────────────────┘
```

### Pattern 2: Continuous Dispatch Scheduling
**What:** No wave barriers — dispatch new tasks immediately as workers complete
**When to use:** GSD phase execution with multiple plans
**Why:** 3-8x faster than sequential, avoids bottlenecks
**Example flow:**
```
T01 starts → T02 starts → T03 starts
    ↓
T01 done → T04 starts IMMEDIATELY (even if T02, T03 still running)
    ↓
T02 done → T05 starts IMMEDIATELY
```

### Pattern 3: Orchestrator-Worker with Lead Agent
**What:** Lead agent (main Claude session) coordinates subagents
**When to use:** Complex tasks requiring strategy + execution
**Reference:** Anthropic's multi-agent research system
**Key points:**
- Lead agent maintains research plan in external memory
- Spawn 3-5 subagents in parallel (not sequentially)
- Subagents write results to filesystem, not through lead agent
- Currently synchronous (lead waits for all); async is future optimization

### Pattern 4: Auto-Init with Notification
**What:** Detect parallelizable work and auto-initialize swarm
**When to use:** User's vision — hybrid approach
**Implementation:**
```python
def detect_swarm_worthy(task_description: str) -> bool:
    """Detect if task benefits from swarm execution."""
    indicators = [
        "multiple plans",
        "parallel",
        "in parallel",
        "simultaneously",
        len(extract_subtasks(task_description)) >= 3,
    ]
    return any(indicators)

# On detection:
# 1. Initialize swarm silently
# 2. Notify user: "Swarm initialized for parallel execution"
# 3. Proceed with dispatch
```

### Anti-Patterns to Avoid
- **Wave-based scheduling:** Waiting for all tasks in a "wave" before starting next batch — causes bottlenecks
- **Coordinator bottleneck:** All results flowing through lead agent — use filesystem/memory instead
- **Free-form swarm:** No structure for tasks that need tight coordination — use agent graph/hierarchical mesh
- **Synchronous everything:** Sequential subagent execution — use parallel spawning
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Swarm lifecycle | Custom process management | `hive-mind init/spawn/shutdown` | Edge cases (orphans, crashes, cleanup) |
| Worker coordination | Custom message passing | `hive-mind broadcast/memory` | Already handles serialization, timing |
| Consensus voting | Custom voting logic | `hive-mind consensus` | Byzantine fault tolerance built-in |
| Task distribution | Custom dispatch loop | `hive-mind task` | Load balancing, priority handling |
| File locking | Custom lock files | Phase 4 `file_claim.py` | Already verified, handles conflicts |
| Orphan cleanup | Manual tracking | `stuck_detector.py` | Session end handling proven |
| CLI wrapper | Direct subprocess calls | `mcp_client.py` | Timeout, error handling, logging |

**Key insight:** claude-flow v3.0 has comprehensive swarm primitives. The existing coordination hooks (Phase 4) handle file-level conflicts. Build the integration layer, not the infrastructure.

</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Hallucination Cascades
**What goes wrong:** One agent's error snowballs as others build on faulty outputs
**Why it happens:** Workers trust each other's outputs without validation
**How to avoid:** Implement quality gates before merge (IOSM pattern), cross-verify critical outputs
**Warning signs:** Compounding errors, inconsistent results across workers
**Stats:** 38% of enterprises report this issue (2025 study)

### Pitfall 2: Thundering Herd on Retry
**What goes wrong:** All failed tasks retry simultaneously, overwhelming system
**Why it happens:** Fixed retry intervals without jitter
**How to avoid:** Exponential backoff with jitter: `delay = base * 2^attempt + random(0, base)`
**Warning signs:** System overwhelmed after recovery, retry storms

### Pitfall 3: Context Window Exhaustion
**What goes wrong:** Long-running swarm sessions exceed context limits
**Why it happens:** Accumulating conversation history across many agent turns
**How to avoid:**
- Store results in external memory (filesystem/hive-memory)
- Spawn fresh subagents for new phases
- Careful handoffs with context summarization
**Warning signs:** Degrading quality, 50%+ context usage

### Pitfall 4: Circular Dependencies
**What goes wrong:** Tasks depend on each other creating deadlock
**Why it happens:** Poor task decomposition, implicit dependencies
**How to avoid:** Explicit dependency graph, topological sort before dispatch
**Warning signs:** Tasks stuck waiting, no progress despite healthy workers

### Pitfall 5: Orphaned Claims
**What goes wrong:** Crashed session leaves claims locked, blocking other agents
**Why it happens:** No cleanup on abnormal termination
**How to avoid:** Already solved by `stuck_detector.py` (Stop hook) — ensure it's registered
**Warning signs:** Blocked edits with "claimed by another agent"
</common_pitfalls>

<code_examples>
## Code Examples

Verified patterns from claude-flow CLI and existing hooks:

### Swarm Lifecycle Manager (skeleton)
```python
#!/usr/bin/env python3
"""Hive Manager Hook - Swarm lifecycle for GSD phase execution."""

import json
import subprocess
from pathlib import Path

def _run_hive_cmd(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Run claude-flow hive-mind command."""
    cmd = ["npx", "-y", "claude-flow@latest", "hive-mind"] + args
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=str(Path.home())
    )
    return result.returncode == 0, result.stdout or result.stderr

def init_swarm(topology: str = "hierarchical-mesh") -> dict:
    """Initialize hive-mind swarm."""
    success, output = _run_hive_cmd(["init", "-t", topology])
    return {"success": success, "output": output}

def spawn_workers(count: int = 3) -> dict:
    """Spawn workers into hive."""
    success, output = _run_hive_cmd(["spawn", "-n", str(count)])
    return {"success": success, "output": output}

def submit_task(description: str) -> dict:
    """Submit task to hive."""
    success, output = _run_hive_cmd(["task", "-d", description])
    return {"success": success, "output": output}

def get_status(verbose: bool = True) -> dict:
    """Get hive status."""
    args = ["status"]
    if verbose:
        args.append("--verbose")
    success, output = _run_hive_cmd(args)
    return {"success": success, "output": output}

def shutdown_swarm(graceful: bool = True) -> dict:
    """Shutdown hive-mind."""
    success, output = _run_hive_cmd(["shutdown"])
    return {"success": success, "output": output}
```

### Retry with Exponential Backoff + Jitter
```python
import random
import time

def retry_with_backoff(
    fn,
    max_retries: int = 2,
    base_delay: float = 1.0,
    max_delay: float = 30.0
) -> tuple[bool, any]:
    """Retry function with exponential backoff and jitter."""
    for attempt in range(max_retries + 1):
        try:
            result = fn()
            return True, result
        except Exception as e:
            if attempt == max_retries:
                return False, str(e)

            # Exponential backoff with jitter
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, base_delay)
            time.sleep(delay + jitter)

    return False, "max retries exceeded"
```

### Task Complexity Detection
```python
def detect_parallelizable(task_input: dict) -> bool:
    """Detect if task is swarm-worthy based on complexity signals."""
    description = task_input.get("description", "") or task_input.get("prompt", "")

    # Explicit parallel signals
    parallel_keywords = ["parallel", "simultaneously", "concurrent", "in parallel"]
    if any(kw in description.lower() for kw in parallel_keywords):
        return True

    # Multiple subtasks (e.g., numbered list)
    import re
    numbered_items = re.findall(r'^\s*\d+[.)]\s', description, re.MULTILINE)
    if len(numbered_items) >= 3:
        return True

    # Multiple file mentions
    file_mentions = re.findall(r'\b[\w/]+\.(py|ts|js|md|json)\b', description)
    if len(set(file_mentions)) >= 4:
        return True

    return False
```
</code_examples>

<sota_updates>
## State of the Art (2025-2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sequential subagent execution | Parallel 3-5 subagents | 2025 (Anthropic research) | Up to 90% time reduction |
| Results through coordinator | Filesystem/memory artifacts | 2025 | Reduces token overhead |
| Wave-based batch scheduling | Continuous dispatch | 2025 | 3-8x faster execution |
| Manual retry timing | Exponential backoff + jitter | Standard practice | Prevents thundering herd |
| Single-agent context | Distributed memory + handoffs | 2025 | Enables longer workflows |

**New patterns to consider:**
- **Swarm-IOSM quality gates:** I/O/S/M metrics before merge (Gate-I ≥0.95 semantic coherence)
- **Hierarchical-mesh topology:** Hybrid of hierarchical control + mesh flexibility (claude-flow v3 default)
- **Artifact-based communication:** Workers write to filesystem, pass lightweight references

**Deprecated/outdated:**
- **Wave barriers:** Waiting for entire batch before next — use continuous dispatch
- **Coordinator as message bus:** All results through lead agent — use shared memory
- **OpenAI Swarm (experimental):** Replaced by production Agents SDK (March 2025)
</sota_updates>

<open_questions>
## Open Questions

Things that couldn't be fully resolved:

1. **claude-flow MCP server connection status**
   - What we know: MCP tools exist but server showed "not connected" during research
   - What's unclear: Whether CLI works reliably when MCP is disconnected
   - Recommendation: Use CLI (`npx claude-flow`) as primary interface (proven in Phase 4)

2. **Async subagent execution**
   - What we know: Current Task tool execution is synchronous (main Claude waits)
   - What's unclear: If/when async dispatch becomes available
   - Recommendation: Design for async-ready (continuous dispatch) but implement sync first

3. **Optimal worker count**
   - What we know: Anthropic uses 3-5 subagents, Swarm-IOSM uses 3-6
   - What's unclear: Optimal count for GSD phase execution specifically
   - Recommendation: Start with 3, allow configuration, measure results
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- claude-flow v3.0.0-alpha.136 CLI help output — all hive-mind commands verified
- Existing Phase 4 hooks in `/media/sam/1TB/claude-hooks-shared/hooks/coordination/` — patterns proven in production
- `mcp_client.py` — established CLI wrapper pattern

### Secondary (MEDIUM confidence)
- [Anthropic Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) — verified architecture patterns
- [Swarm-IOSM: Orchestrating Parallel AI Agents](https://dev.to/rokoss21/swarm-iosm-orchestrating-parallel-ai-agents-with-quality-gates-8fk) — continuous dispatch, quality gates
- [Four Design Patterns for Event-Driven Multi-Agent Systems](https://www.confluent.io/blog/event-driven-multi-agent-systems/) — orchestrator-worker pattern
- [AWS Timeouts, Retries and Backoff with Jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) — retry pattern best practices

### Tertiary (verified against multiple sources)
- [Multi-Agent Coordination Strategies](https://galileo.ai/blog/multi-agent-coordination-strategies) — hallucination cascade stats (38%)
- [Top AI Agent Architectures 2025](https://www.marktechpost.com/2025/11/15/comparing-the-top-5-ai-agent-architectures-in-2025-hierarchical-swarm-meta-learning-modular-evolutionary/) — swarm vs agent graph patterns
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: claude-flow v3.0 hive-mind commands
- Ecosystem: Existing Phase 4 coordination hooks, mcp_client.py
- Patterns: Orchestrator-worker, continuous dispatch, two-layer coordination
- Pitfalls: Hallucination cascades, thundering herd, context exhaustion, circular dependencies

**Confidence breakdown:**
- Standard stack: HIGH — verified with claude-flow CLI help
- Architecture: HIGH — patterns from Anthropic + verified with existing codebase
- Pitfalls: HIGH — documented in multiple 2025 sources, cross-verified
- Code examples: HIGH — based on existing Phase 4 hooks + official patterns

**Research date:** 2026-01-20
**Valid until:** 2026-02-20 (30 days — claude-flow actively developed)
</metadata>

---

*Phase: 05-swarm-intelligence*
*Research completed: 2026-01-20*
*Ready for planning: yes*
