# ROADMAP: Claude-Flow Systematic Integration

## Milestone: v1.0 - Automatic Learning Infrastructure

### Phase 1: Session Recovery (Quick Win)
**Goal:** Automatic session save/restore for crash recovery

**Deliverables:**
- `hooks/session/session_checkpoint.py` - Stop hook that saves session
- `hooks/session/session_restore_check.py` - UserPromptSubmit hook that checks for interrupted sessions
- Verification: Simulate crash, verify recovery prompt appears

**Verification Criteria:**
- [ ] session_checkpoint.py creates checkpoint on Stop
- [ ] session_restore_check.py detects interrupted session
- [ ] claude-flow memory shows session entries
- [ ] Hook registered in settings.json and executes

---

### Phase 2: Trajectory Learning (SONA)
**Goal:** Track agent trajectories for learning

**Deliverables:**
- `hooks/intelligence/trajectory_tracker.py` - Pre/Post/Stop hooks for Task tool
- Verification: Spawn Task agent, verify trajectory recorded

**Verification Criteria:**
- [ ] trajectory_tracker.py starts trajectory on PreToolUse(Task)
- [ ] trajectory_tracker.py records steps on PostToolUse(Task)
- [ ] trajectory_tracker.py ends trajectory on Stop
- [ ] claude-flow intelligence stats show trajectories > 0

---

### Phase 3: Lesson Learning & Injection
**Goal:** Extract patterns from sessions and reinject them

**Deliverables:**
- `hooks/intelligence/meta_learning.py` - Stop hook that extracts lessons
- `hooks/intelligence/lesson_injector.py` - UserPromptSubmit hook that injects relevant lessons
- Verification: Complete session with learnable pattern, verify injection in next session

**Verification Criteria:**
- [ ] meta_learning.py extracts patterns (high rework, errors)
- [ ] Patterns stored in claude-flow (pattern-store)
- [ ] lesson_injector.py searches and injects patterns
- [ ] Patterns appear in additionalContext

---

### Phase 4: Coordination & Claims
**Goal:** Multi-agent work distribution with file-level locking

**Deliverables:**
- `hooks/coordination/file_claim.py` - PreToolUse hook for Write|Edit|MultiEdit
- `hooks/coordination/file_release.py` - PostToolUse hook for Write|Edit|MultiEdit
- `hooks/coordination/task_claim.py` - PreToolUse hook for Task (informational)
- `hooks/coordination/task_release.py` - SubagentStop hook
- `hooks/coordination/stuck_detector.py` - Stop hook to mark orphaned claims
- `hooks/coordination/claims_dashboard.py` - Utility to view claims board

**Verification Criteria:**
- [x] file_claim.py claims files before edit operations
- [x] file_release.py releases files after edit operations
- [x] task_claim.py tracks task agent spawns (informational, non-blocking)
- [x] task_release.py releases task claims on SubagentStop
- [x] stuck_detector.py marks active claims as stealable on Stop
- [x] claims_dashboard.py displays formatted claims board

---

### Phase 5: Swarm Intelligence
**Goal:** Hive-mind for complex parallel work

**Deliverables:**
- `hooks/swarm/hive_manager.py` - Swarm lifecycle
- `/swarm` skill command for manual control
- Verification: Initialize swarm, spawn workers, reach consensus

**Verification Criteria:**
- [x] hive_manager.py can init/spawn/status swarm
- [x] /swarm command works
- [x] Swarm appears in claude-flow hive-mind status
- [x] Consensus mechanism ready (propose_consensus function)

---

## Progress Tracking

| Phase | Status | Verified |
|-------|--------|----------|
| Phase 1: Session Recovery | **VERIFIED** | [x] All 5 UAT tests passed |
| Phase 2: Trajectory Learning | **VERIFIED** | [x] All 6 UAT tests passed |
| Phase 3: Lesson Learning | **VERIFIED** | [x] All 56 tests passed |
| Phase 4: Coordination | **VERIFIED** | [x] All hooks registered and tested |
| Phase 5: Swarm | **VERIFIED** | [x] Init/spawn/status/shutdown working |

### Phase 1 Verification Results
- session_checkpoint.py: Writes to `~/.claude-flow/memory/store.json`
- session_restore_check.py: Reads from same store, detects completed sessions
- MCP `memory_retrieve` can see entries created by hooks
- Discovery: CLI and MCP use **different** databases (SQLite vs JSON)

### Phase 2 Verification Results
- trajectory_tracker.py: Registered for PreToolUse(Task), PostToolUse(Task), Stop
- Start event: Creates trajectory with id, project, task, status
- Step event: Records steps with action, success, quality
- End event: Completes trajectory with success_rate calculation
- MCP store: Trajectories stored and indexed for retrieval

### Phase 3 Verification Results
- meta_learning.py (Stop hook): Extracts patterns from session data
  - Detects high_rework (>3 edits on same file)
  - Detects high_error (>25% error rate)
  - Detects quality_drop (declining trend)
  - Stores patterns via pattern_store() with confidence scores
- lesson_injector.py (UserPromptSubmit hook): Injects lessons
  - Searches patterns via pattern_search()
  - HIGH (>0.8): Auto-inject
  - MEDIUM (0.5-0.8): "Consider:" prefix
  - LOW (<0.5): Skip
  - Max 3 lessons to avoid context pollution
- Tests: 34 (meta_learning) + 14 (lesson_injector) + 8 (integration) = 56 total

### Phase 4 Verification Results
- file_claim.py (PreToolUse): Claims files via `npx claude-flow claims claim`
  - Creates file:// issues in claims store
  - Blocks if file already claimed by different session
  - Returns {decision: "block"} on conflict
- file_release.py (PostToolUse): Releases files and broadcasts
  - Uses `npx claude-flow claims release` and `hooks notify`
  - Logs to /tmp/claude-metrics/coordination.log
- task_claim.py (PreToolUse): Tracks task spawns (informational only)
  - Never blocks, always returns {}
  - Generates task_id from description hash + timestamp
- task_release.py (SubagentStop): Releases task claims
  - Gracefully handles no active claims
  - Broadcasts completion notifications
- stuck_detector.py (Stop): Marks orphaned claims as stealable
  - Reads directly from ~/.claude-flow/claims/claims.json
  - Uses `npx claude-flow claims mark-stealable`
- claims_dashboard.py (utility): Displays formatted claims board
  - Supports --json, --watch, --interval flags
  - Shows ACTIVE, STEALABLE, and summary sections

### Phase 5 Verification Results
- hive_manager.py: Full lifecycle management via claude-flow hive-mind CLI
  - init_swarm(): Creates hive with topology (default: hierarchical-mesh)
  - spawn_workers(): Spawns N workers into hive
  - submit_task(): Submits tasks for parallel execution
  - get_status(): Returns hive status (workers, tasks, health)
  - propose_consensus(): Proposes consensus votes
  - broadcast_message(): Messages workers
  - shutdown_swarm(): Graceful/force shutdown
- /swarm skill: Manual control via Claude Code
  - Commands: init, status, spawn, task, shutdown
  - KISS output: minimal confirmation messages
- Logging: /tmp/claude-metrics/swarm.log

---
*Created: 2026-01-20*
*Updated: 2026-01-20 - Phase 5 verified*
