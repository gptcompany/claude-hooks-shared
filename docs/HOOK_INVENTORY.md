# Hook Inventory & Usage Guide

**Last Updated**: 2025-10-27
**Total Hooks**: 11 files (8 Python, 1 Bash, 2 SQL)

---

## 📊 Hook Classification

### Tier 1: Essential (All Projects) ⭐⭐⭐

| Hook | Event | Purpose | Dependencies |
|------|-------|---------|--------------|
| `stop.py` | Stop | Voice "Work complete!" | `spd-say` (Linux) / `say` (macOS) |
| `notification.py` | UserPromptSubmit | Voice "Agent needs input" | `spd-say` (Linux) / `say` (macOS) |
| `git-safety-check.py` | PreToolUse (Bash) | Block force push, secrets | None |
| `smart-safety-check.py` | PreToolUse (Bash) | CCundo checkpoint + confirm | `ccundo` |

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
