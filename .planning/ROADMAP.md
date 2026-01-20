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
**Goal:** Multi-agent work distribution

**Deliverables:**
- `hooks/coordination/orchestrator.py` - Multi-agent coordination
- `hooks/coordination/claims_manager.py` - Work claim/release
- Verification: Run parallel Task agents, verify claims tracked

**Verification Criteria:**
- [ ] orchestrator.py initializes topology for multi-agent
- [ ] claims_manager.py claims work on PreToolUse(Task)
- [ ] claims_manager.py releases on SubagentStop
- [ ] claude-flow claims_board shows distribution

---

### Phase 5: Swarm Intelligence
**Goal:** Hive-mind for complex parallel work

**Deliverables:**
- `hooks/swarm/hive_manager.py` - Swarm lifecycle
- `/swarm` skill command for manual control
- Verification: Initialize swarm, spawn workers, reach consensus

**Verification Criteria:**
- [ ] hive_manager.py can init/spawn/status swarm
- [ ] /swarm command works
- [ ] Swarm appears in claude-flow hive-mind_status
- [ ] Consensus mechanism works

---

## Progress Tracking

| Phase | Status | Verified |
|-------|--------|----------|
| Phase 1: Session Recovery | **VERIFIED** | [x] All 5 UAT tests passed |
| Phase 2: Trajectory Learning | **VERIFIED** | [x] All 6 UAT tests passed |
| Phase 3: Lesson Learning | **VERIFIED** | [x] All 56 tests passed |
| Phase 4: Coordination | pending | [ ] |
| Phase 5: Swarm | pending | [ ] |

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

---
*Created: 2026-01-20*
*Updated: 2026-01-20 - Phase 3 verified*
