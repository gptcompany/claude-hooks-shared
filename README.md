# Claude Code Hook System - Multi-Repository Template

**Version**: 3.0 (Complete Hook Collection)
**Author**: Consolidated from N8N_dev + UTXOracle implementations
**Purpose**: Reusable Claude Code hooks for session tracking, safety, and UX across multiple repositories

---

## 📦 What's Included

### **Core Session Tracking** (Multi-Project)
- `context_bundle_builder.py` - Pre-tool-use hook (logs operations)
- `post-tool-use.py` - Post-tool-use hook (tracks duration + errors)
- `session_manager.py` - PostgreSQL wrapper (CRUD operations)
- `session-end.sh` - Session cleanup + N8N webhook trigger

### **Safety & Protection Hooks**
- `git-safety-check.py` - Git operation protection (force push, secrets, large files)
- `smart-safety-check.py` - Intelligent command safety (checkpoint + confirm + CWD limit)

### **UX Enhancement Hooks**
- `stop.py` - Voice announcement "Work complete!" (TTS)
- `notification.py` - Voice alert "Agent needs your input" (TTS)

### **Developer Productivity**
- `auto-format.py` - Automatic Ruff formatting after Python edits
- `subagent-checkpoint.sh` - Auto-commit after subagent completion

### **Database Management**
- `init_db.py` - Create PostgreSQL schema
- `migrate_add_project_name.sql` - Migration for multi-repo support

### **Documentation**
- `GIT_SAFETY_GUIDE.md` - Git safety hook details
- `SMART_SAFETY_GUIDE.md` - Smart safety philosophy
- `AUTO_FORMAT_GUIDE.md` - Auto-format configuration
- `CLAUDE_STRUCTURE_AUTO_UPDATE.md` - Repository structure updater docs

---

## 🎯 Features

✅ **Multi-repository support** via `CLAUDE_PROJECT_NAME` env variable
✅ **Dual architecture support**: PostgreSQL direct write OR N8N workflow
✅ **Git safety**: Prevents force push, secret leaks, large file commits
✅ **Smart safety**: CCundo checkpoint + CWD limit for dangerous commands
✅ **Voice notifications**: TTS announcements for completion and alerts
✅ **Auto-formatting**: Ruff integration for Python code quality
✅ **Subagent tracking**: Auto-commit after Task tool execution
✅ **No hardcoded paths**: Works in any repository structure
✅ **Error pattern detection**: TDD blocks, timeouts, hook blocks
✅ **Real-time metrics**: Token usage, cost tracking, git metrics

---

## 🚀 Installation Guide

### Prerequisites

1. **PostgreSQL 12+** with database `claude_sessions`
2. **Python 3.11+** with `psycopg2` installed
3. **Claude Code** with hook support

```bash
# Install dependencies
pip install psycopg2-binary

# Or with uv
uv pip install psycopg2-binary
```

---

### Step 1: Database Migration (ONCE)

**If this is your FIRST repository**:
```bash
# Create database schema
python3 /media/sam/1TB/claude-hooks-shared/init_db.py
```

**If you ALREADY have existing data** (upgrading from single-repo):
```bash
# Add project_name columns
psql -U your_user -d claude_sessions -f /media/sam/1TB/claude-hooks-shared/migrate_add_project_name.sql
```

**Verify migration**:
```bash
psql -U your_user -d claude_sessions -c "
SELECT column_name FROM information_schema.columns
WHERE table_name = 'sessions' AND column_name = 'project_name';
"
```

---

### Step 2: Install Hooks in Target Repository

**Example: Installing in UTXOracle**

```bash
# Navigate to target repository
cd /media/sam/1TB/UTXOracle

# Create directory structure
mkdir -p .claude/hooks
mkdir -p .claude/scripts
mkdir -p .claude/context_bundles
mkdir -p .claude/logs

# Copy hook files
cp /media/sam/1TB/claude-hooks-shared/context_bundle_builder.py .claude/hooks/
cp /media/sam/1TB/claude-hooks-shared/post-tool-use.py .claude/hooks/
cp /media/sam/1TB/claude-hooks-shared/session-end.sh .claude/hooks/
cp /media/sam/1TB/claude-hooks-shared/session_manager.py .claude/scripts/

# Make executable
chmod +x .claude/hooks/*.py
chmod +x .claude/hooks/*.sh
```

---

### Step 3: Configure Hooks in settings.local.json

Create or edit `.claude/settings.local.json`:

```json
{
  "hooks": {
    "preToolUse": {
      "command": "./.claude/hooks/context_bundle_builder.py",
      "env": {
        "CLAUDE_PROJECT_NAME": "UTXOracle",
        "DATABASE_URL": "postgresql://localhost:5432/claude_sessions"
      }
    },
    "postToolUse": {
      "command": "./.claude/hooks/post-tool-use.py",
      "env": {
        "CLAUDE_PROJECT_NAME": "UTXOracle",
        "DATABASE_URL": "postgresql://localhost:5432/claude_sessions"
      }
    },
    "sessionEnd": {
      "command": "./.claude/hooks/session-end.sh",
      "env": {
        "CLAUDE_PROJECT_NAME": "UTXOracle"
      }
    }
  }
}
```

**⚠️ IMPORTANT**: Change `CLAUDE_PROJECT_NAME` to your repository name!

---

### Step 4: Test Installation

**Manual test**:
```bash
# Test context_bundle_builder.py
echo '{"session_id":"test-123","tool_name":"Read","tool_input":{"file_path":"test.py"}}' | \
  CLAUDE_PROJECT_NAME=UTXOracle ./.claude/hooks/context_bundle_builder.py

# Verify file created
ls -la .claude/context_bundles/

# Verify PostgreSQL write
psql -U your_user -d claude_sessions -c "
SELECT session_id, project_name, tool_name
FROM tool_usage
WHERE project_name = 'UTXOracle'
ORDER BY timestamp DESC LIMIT 5;
"
```

**Live test with Claude Code**:
```bash
# Start Claude Code session
# Execute some operations (Read, Edit, etc.)
# Check logs for hook execution
```

---

## 📊 Querying Multi-Project Data

### Query sessions by project:
```sql
SELECT session_id, started_at, git_branch, total_cost_usd
FROM sessions
WHERE project_name = 'UTXOracle'
ORDER BY started_at DESC LIMIT 10;
```

### Compare tool usage across projects:
```sql
SELECT project_name, tool_name, COUNT(*) as usage_count
FROM tool_usage
GROUP BY project_name, tool_name
ORDER BY project_name, usage_count DESC;
```

### Find errors by project:
```sql
SELECT project_name, event_type, COUNT(*) as error_count
FROM events
GROUP BY project_name, event_type
ORDER BY error_count DESC;
```

### Total cost per project:
```sql
SELECT project_name, SUM(total_cost_usd) as total_cost, COUNT(*) as session_count
FROM sessions
GROUP BY project_name
ORDER BY total_cost DESC;
```

---

## 🔧 Customization

### Project-Specific Config

Create `.claude/config.json` in your repository:

```json
{
  "project_name": "UTXOracle",
  "database_url": "postgresql://localhost:5432/claude_sessions"
}
```

### Optional: Context Monitor

For real-time token monitoring, copy `context-monitor.py`:

```bash
cp /media/sam/1TB/claude-hooks-shared/context-monitor.py .claude/scripts/
```

Configure in `.claude/settings.local.json`:

```json
{
  "statusLine": {
    "command": "./.claude/scripts/context-monitor.py",
    "interval": 2000
  }
}
```

---

## 🐛 Troubleshooting

### Hooks not executing
```bash
# Check file permissions
ls -la .claude/hooks/

# Should see -rwxr-xr-x permissions
# If not, run:
chmod +x .claude/hooks/*.py
```

### Database connection errors
```bash
# Verify PostgreSQL running
psql -U your_user -d claude_sessions -c "\dt"

# Check DATABASE_URL in settings.local.json
# Format: postgresql://user:password@host:port/database
```

### project_name is NULL in database
```bash
# Verify CLAUDE_PROJECT_NAME env variable set in hooks config
# Check settings.local.json has "env": {"CLAUDE_PROJECT_NAME": "YourProject"}
```

### Import errors (session_manager not found)
```bash
# Verify session_manager.py exists in .claude/scripts/
ls -la .claude/scripts/session_manager.py

# Check Python can import it
cd .claude/scripts && python3 -c "import session_manager; print('OK')"
```

---

## 📚 Architecture

### Data Flow:

```
Claude Code Tool Call
    ↓
[PreToolUse] context_bundle_builder.py
    ├─→ Write to .claude/context_bundles/<session>.json (file backup)
    └─→ INSERT INTO tool_usage (PostgreSQL, duration=0)
    ↓
[Tool Executes]
    ↓
[PostToolUse] post-tool-use.py
    ├─→ Calculate duration from temp file
    ├─→ UPDATE tool_usage (duration, success, error)
    └─→ INSERT INTO events (if error detected)
```

### Database Schema:

**sessions** table:
- `session_id` (PK), `project_name`, `git_branch`, `started_at`
- `total_tokens_input`, `total_tokens_output`, `total_cost_usd`
- `task_description`, `agent_name`

**tool_usage** table:
- `id` (PK), `session_id`, `project_name`, `tool_name`
- `tool_params` (JSONB), `timestamp`, `duration_ms`
- `success` (boolean), `error` (text)

**events** table:
- `id` (PK), `session_id`, `project_name`, `event_type`
- `timestamp`, `tool_name`, `error_message`, `severity`

---

## 🔄 Updating Existing Repositories

If you already have hooks installed (e.g., in N8N_dev), update to multi-project version:

```bash
cd /media/sam/1TB/N8N_dev

# Backup current hooks
cp -r .claude/hooks .claude/hooks.backup

# Update hook files
cp /media/sam/1TB/claude-hooks-shared/context_bundle_builder.py .claude/hooks/
cp /media/sam/1TB/claude-hooks-shared/post-tool-use.py .claude/hooks/
cp /media/sam/1TB/claude-hooks-shared/session_manager.py .claude/scripts/

# Update settings.local.json to add CLAUDE_PROJECT_NAME env variable
# (See Step 3 above)
```

---

## 📝 Best Practices

1. **Use descriptive project names**: `UTXOracle`, `N8N_dev`, not `repo1`, `test`
2. **Keep DATABASE_URL consistent**: All repos should point to same PostgreSQL
3. **Backup context_bundles/**: Useful for debugging when PostgreSQL is down
4. **Monitor database size**: Run cleanup scripts periodically (see N8N_dev example)
5. **Test hooks after installation**: Don't assume they work, verify with manual test

---

## 📖 Related Documentation

- **N8N_dev implementation**: `/media/sam/1TB/N8N_dev/CLAUDE.md`
- **Session analysis guide**: `/media/sam/1TB/N8N_dev/specs/001-specify-scripts-bash/SESSION_ANALYSIS_GUIDE.md`
- **PostgreSQL schema**: Run `.schema` in psql on `claude_sessions` database

---

## 🤝 Contributing

Found a bug or want to improve the template? Update files in `/media/sam/1TB/claude-hooks-shared/` and re-deploy to your repositories.

**Deployment checklist**:
1. Update file in `/media/sam/1TB/claude-hooks-shared/`
2. Test in one repository
3. Deploy to other repositories
4. Update this README

---

## 📄 License

Open source. Use freely in your Claude Code projects.
