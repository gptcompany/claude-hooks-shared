# Hook Inventory & Usage Guide

**Last Updated**: 2026-01-12
**Total Hooks**: 14 files (11 Python, 1 Bash, 2 SQL)

---

## 📊 Hook Classification

### Tier 1: Essential (All Projects) ⭐⭐⭐

| Hook | Event | Purpose | Dependencies |
|------|-------|---------|--------------|
| `stop.py` | Stop | Voice "Work complete!" | `spd-say` (Linux) / `say` (macOS) |
| `notification.py` | UserPromptSubmit | Voice "Agent needs input" | `spd-say` (Linux) / `say` (macOS) |
| `git-safety-check.py` | PreToolUse (Bash) | Block force push, secrets | None |
| `smart-safety-check.py` | PreToolUse (Bash) | CCundo checkpoint + confirm | `ccundo` |

### Tier 1.5: Intelligent Session Context ⭐⭐⭐ (NEW)

| Hook | Event | Purpose | Output |
|------|-------|---------|--------|
| `session_analyzer.py` | Stop | Analyze session + save stats | `[uncommitted: +100/-20] [session: 45 calls, 8 errors] [suggest: /review]` |
| `session_start_tracker.py` | UserPromptSubmit | Inject previous session stats | `[prev session: ...] [tracking: main@abc123]` |

**Flow**:
1. Session N ends → `session_analyzer.py` saves stats to `~/.claude/metrics/last_session_stats.json`
2. Session N+1 starts → `session_start_tracker.py` injects stats into `additionalContext`
3. Stats file cleared after injection (one-time use)

**Contextual Suggestions** (rule-based):
| Condition | Suggestion | Priority |
|-----------|------------|----------|
| Error rate > 25% AND errors >= 5 | `/undo:checkpoint` | 1 (safety) |
| Config files >= 2 | `/health` | 2 (safety) |
| Lines added >= 50 | `/review` | 3 (quality) |
| Tool calls >= 60 | `/context` | 4 (convenience) |

**vs /tips command**:
- Hook = automatic, single session, rule-based
- /tips = manual, multi-session QuestDB analysis, statistical (z-scores)

### Tier 2: Core Session Tracking ⭐⭐

| Hook | Event | Purpose | Architecture |
|------|-------|---------|--------------|
| `context_bundle_builder.py` | PreToolUse | Log operations start | Multi-project OR N8N |
| `post-tool-use.py` | PostToolUse | Track duration + errors | Multi-project OR N8N |
| `session-end.sh` | SessionEnd | Git metrics + webhook | N8N workflow trigger |
| `session_manager.py` | (Library) | PostgreSQL CRUD | Multi-project only |

### Tier 3: Optional Productivity ⭐

| Hook | Event | Purpose | Dependencies |
|------|-------|---------|--------------|
| `auto-format.py` | PostToolUse (Write/Edit) | Ruff auto-format | `uv`, `ruff` |
| `subagent-checkpoint.sh` | SubagentStop | Auto-commit after Task | Git, `jq` |

### Tier 4: Experimental/Research 🧪

| Hook | Event | Purpose | Dependencies |
|------|-------|---------|--------------|
| `verbalized_sampling.py` | UserPromptSubmit | A/B test: Claude Sonnet 4.5 vs Gemini 2.5 Pro (Verbalized Sampling) | `mcp__gemini-cli__ask-gemini` |

**Usage**: `/vsample [N] <request>` (e.g., `/vsample 5 write a haiku about Bitcoin`)

**Output**: Comparative analysis of creative generation quality between Claude and Gemini

---

## 🏗️ Architecture Patterns

### Pattern A: N8N Centralized (N8N_dev)

**Philosophy**: Minimal hooks + N8N workflow handles analysis

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": ["smart-safety-check.py", "git-safety-check.py"]}
    ],
    "PostToolUse": [
      {"matcher": "Write|Edit", "hooks": ["auto-format.py"]},
      {"matcher": "", "hooks": ["post-tool-use.py", "context_bundle_builder.py"]}
    ],
    "Stop": [{"hooks": ["stop.py"]}],
    "UserPromptSubmit": [{"hooks": ["notification.py"]}],
    "SubagentStop": [{"hooks": ["subagent-checkpoint.sh"]}],
    "SessionEnd": [{"hooks": ["session-end.sh"]}]
  }
}
```

**Data Flow**:
```
Hooks (minimal) → session-end.sh → N8N webhook → AI Agent → PostgreSQL
```

**Hook responsibilities**:
- ✅ Safety checks (git, bash commands)
- ✅ Voice notifications
- ✅ Auto-format
- ✅ File-based tracking
- ❌ NO PostgreSQL write (N8N handles)

---

### Pattern B: Multi-Project Direct (UTXOracle)

**Philosophy**: Hooks write directly to PostgreSQL

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": ["smart-safety-check.py", "git-safety-check.py"]},
      {"matcher": "", "hooks": ["context_bundle_builder.py"], "env": {
        "CLAUDE_PROJECT_NAME": "YourProject",
        "DATABASE_URL": "postgresql://localhost:5432/claude_sessions"
      }}
    ],
    "PostToolUse": [
      {"matcher": "Write|Edit", "hooks": ["auto-format.py"]},
      {"matcher": "", "hooks": ["post-tool-use.py"], "env": {
        "CLAUDE_PROJECT_NAME": "YourProject",
        "DATABASE_URL": "postgresql://localhost:5432/claude_sessions"
      }}
    ],
    "Stop": [{"hooks": ["stop.py"]}],
    "UserPromptSubmit": [{"hooks": ["notification.py"]}],
    "SubagentStop": [{"hooks": ["subagent-checkpoint.sh"]}],
    "SessionEnd": [{"hooks": ["session-end.sh"]}]
  }
}
```

**Data Flow**:
```
Hooks → Direct PostgreSQL → (Optional: N8N webhook for notifications)
```

**Hook responsibilities**:
- ✅ Safety checks
- ✅ Voice notifications
- ✅ Auto-format
- ✅ PostgreSQL write (sessions, tool_usage, events)
- ✅ File-based backup

---

## 🚀 Quick Start by Use Case

### Minimal (Voice + Safety Only)
```json
{
  "hooks": {
    "PreToolUse": [{"matcher": "Bash", "hooks": ["git-safety-check.py"]}],
    "Stop": [{"hooks": ["stop.py"]}],
    "UserPromptSubmit": [{"hooks": ["notification.py"]}]
  }
}
```

### Standard (Voice + Safety + Auto-format)
```json
{
  "hooks": {
    "PreToolUse": [{"matcher": "Bash", "hooks": ["smart-safety-check.py", "git-safety-check.py"]}],
    "PostToolUse": [{"matcher": "Write|Edit", "hooks": ["auto-format.py"]}],
    "Stop": [{"hooks": ["stop.py"]}],
    "UserPromptSubmit": [{"hooks": ["notification.py"]}]
  }
}
```

### Full-Featured (All Hooks)
See Pattern A or Pattern B above.

---

## 📝 Hook Dependencies

| Hook | Requires | Optional |
|------|----------|----------|
| `stop.py` | `spd-say` (Linux) or `say` (macOS) | - |
| `notification.py` | `spd-say` (Linux) or `say` (macOS) | `ENGINEER_NAME` env |
| `git-safety-check.py` | None | - |
| `smart-safety-check.py` | `ccundo` | - |
| `auto-format.py` | `uv`, `ruff` | - |
| `subagent-checkpoint.sh` | `git`, `jq` | - |
| `context_bundle_builder.py` | `session_manager.py` (if PostgreSQL) | `CLAUDE_PROJECT_NAME`, `DATABASE_URL` |
| `post-tool-use.py` | `session_manager.py` (if PostgreSQL) | `CLAUDE_PROJECT_NAME`, `DATABASE_URL` |
| `session-end.sh` | `curl`, `git` | - |
| `verbalized_sampling.py` | `gemini` CLI, `mcp__gemini-cli__ask-gemini` | - |

---

## 🔧 Installation Commands

```bash
# Install TTS (Linux)
sudo apt install speech-dispatcher

# Install Ruff (Python formatter)
uv pip install ruff

# Install CCundo (safety checkpoint)
# See https://github.com/PrincyX/ccundo

# Install jq (JSON processor)
sudo apt install jq
```

---

## 📖 Related Documentation

- **Main README**: `/media/sam/1TB/claude-hooks-shared/README.md`
- **Git Safety**: `/media/sam/1TB/claude-hooks-shared/GIT_SAFETY_GUIDE.md`
- **Smart Safety**: `/media/sam/1TB/claude-hooks-shared/SMART_SAFETY_GUIDE.md`
- **Auto-Format**: `/media/sam/1TB/claude-hooks-shared/AUTO_FORMAT_GUIDE.md`

---

## 🧪 Verbalized Sampling Hook (Experimental)

**Purpose**: Compare creative generation quality between Claude Sonnet 4.5 and Gemini 2.5 Pro using the Verbalized Sampling technique from Stanford CHATS lab.

**Research Paper**: https://github.com/CHATS-lab/verbalized-sampling

### How It Works

1. User types: `/vsample [N] <request>`
2. Hook transforms prompt into dual-track A/B test instructions
3. Claude Sonnet 4.5:
   - Generates N diverse responses (default: 5)
   - Self-selects best response
4. Gemini 2.5 Pro (via MCP):
   - Generates N diverse responses
   - Self-selects best response
5. Output shows comparative analysis

### Example

**Input**:
```
/vsample write a haiku about Bitcoin mining
```

**Output**:
```
═══════════════════════════════════════════════════════════
🎭 VERBALIZED SAMPLING A/B TEST RESULTS
═══════════════════════════════════════════════════════════

📝 Request: "write a haiku about Bitcoin mining"
🔢 Samples per track: 5

───────────────────────────────────────────────────────────
🧠 CLAUDE SONNET 4.5 TRACK
───────────────────────────────────────────────────────────

Generated Responses:
1. (p=0.35) Hashing through the night / Nonce by nonce...
[... 4 more responses ...]

✅ Claude's Selection: #1 (p=0.35)
📌 Reasoning: Best technical accuracy

───────────────────────────────────────────────────────────
🤖 GEMINI 2.5 PRO TRACK
───────────────────────────────────────────────────────────

Generated Responses:
1. (p=0.40) Power plants hum deep / Processors hunt...
[... 4 more responses ...]

✅ Gemini's Selection: #2 (p=0.28)
📌 Reasoning: Poetic balance

───────────────────────────────────────────────────────────
📊 COMPARATIVE ANALYSIS
───────────────────────────────────────────────────────────

• Diversity: Both models show good probability spread
• Creativity: Gemini favors metaphor, Claude favors technical
• Recommendation: Claude for accuracy, Gemini for imagery
═══════════════════════════════════════════════════════════
```

### Configuration

Add to `settings.local.json`:
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/ux/verbalized_sampling.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### Use Cases

- **Creative Writing**: Poetry, jokes, stories
- **Technical Explanations**: Different pedagogical approaches
- **Problem Solving**: Multiple solution strategies
- **Brainstorming**: Diverse ideation
- **A/B Testing**: Evaluate model strengths over time

### Notes

- Default: 5 samples per model (customizable with `/vsample N`)
- Requires `mcp__gemini-cli__ask-gemini` tool access
- KISS architecture: Single hook, Claude orchestrates
- Research context: 1-week A/B testing recommended
