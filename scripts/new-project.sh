#!/bin/bash
set -euo pipefail

# new-project.sh - Bootstrap new Claude Code project with best practices
# Usage: ./new-project.sh --name "ProjectName" --path "/base/path" --data-source "/path/to/data" --agents "agent1,agent2" --tdd-guard

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
PROJECT_NAME=""
BASE_PATH=""
DATA_SOURCE=""
AGENTS=""
TDD_GUARD=false
CLAUDE_HOOKS_SHARED="/media/sam/1TB/claude-hooks-shared"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --name)
      PROJECT_NAME="$2"
      shift 2
      ;;
    --path)
      BASE_PATH="$2"
      shift 2
      ;;
    --data-source)
      DATA_SOURCE="$2"
      shift 2
      ;;
    --agents)
      AGENTS="$2"
      shift 2
      ;;
    --tdd-guard)
      TDD_GUARD=true
      shift
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

# Validate required arguments
if [[ -z "$PROJECT_NAME" || -z "$BASE_PATH" ]]; then
  echo -e "${RED}Error: Missing required arguments${NC}"
  echo "Usage: ./new-project.sh --name \"ProjectName\" --path \"/base/path\" [--data-source \"/path/to/data\"] [--agents \"agent1,agent2\"] [--tdd-guard]"
  exit 1
fi

PROJECT_PATH="$BASE_PATH/$PROJECT_NAME"

echo -e "${GREEN}🚀 Creating new Claude Code project: $PROJECT_NAME${NC}"
echo ""

# 1. Create project directory
if [[ -d "$PROJECT_PATH" ]]; then
  echo -e "${RED}Error: Directory already exists: $PROJECT_PATH${NC}"
  exit 1
fi

mkdir -p "$PROJECT_PATH"
echo -e "${GREEN}✅ Created: $PROJECT_PATH${NC}"

# 2. Create directory structure
echo -e "${YELLOW}📁 Creating directory structure...${NC}"
mkdir -p "$PROJECT_PATH"/{src,tests,scripts,data/{raw,processed,cache},frontend,.claude/{skills,commands,agents,prompts,tdd-guard/data,docs},.serena,.specify}

# 3. Copy .claude template files (generic, no Bitcoin-specific)
echo -e "${YELLOW}📋 Copying .claude configuration...${NC}"

# Copy skills (generic only)
cp -r /media/sam/1TB/UTXOracle/.claude/skills/pytest-test-generator "$PROJECT_PATH/.claude/skills/"
cp -r /media/sam/1TB/UTXOracle/.claude/skills/pydantic-model-generator "$PROJECT_PATH/.claude/skills/"
cp -r /media/sam/1TB/UTXOracle/.claude/skills/github-workflow "$PROJECT_PATH/.claude/skills/"

# Copy SpecKit commands
cp /media/sam/1TB/UTXOracle/.claude/commands/*.md "$PROJECT_PATH/.claude/commands/"

# Copy docs (portable blueprints)
cp /media/sam/1TB/UTXOracle/.claude/docs/SKILLS_FRAMEWORK_BLUEPRINT.md "$PROJECT_PATH/.claude/docs/"

# Copy config.json
cp /media/sam/1TB/UTXOracle/.claude/config.json "$PROJECT_PATH/.claude/config.json"

# 4. Generate settings.local.json (template, no project-specific paths)
echo -e "${YELLOW}⚙️  Generating settings.local.json...${NC}"
cat > "$PROJECT_PATH/.claude/settings.local.json" <<'EOF'
{
  "permissions": {
    "allow": [
      "Read(//home/sam/**)",
      "Edit(//home/sam/**)",
      "Edit(//media/sam/1TB1/**)",
      "MultiEdit(//home/sam/**)",
      "MultiEdit(//media/sam/1TB1/**)",
      "Write(//media/sam/1TB1/**)",
      "mcp__gemini-cli__ask-gemini",
      "WebSearch",
      "mcp__archon__list_projects",
      "mcp__archon__create_project",
      "mcp__archon__delete_project",
      "mcp__context7__get-library-docs",
      "mcp__serena__list_dir",
      "Bash(python:*)",
      "Bash(uv:*)",
      "Bash(git:*)",
      "Bash(pytest:*)",
      "Bash(mkdir:*)",
      "Bash(echo:*)",
      "Read(//media/sam/**)",
      "WebFetch(domain:github.com)"
    ],
    "deny": [
      "Read(.claude/tdd-guard/**)"
    ],
    "ask": [],
    "defaultMode": "bypassPermissions",
    "additionalDirectories": [
      "/media/sam/1TB1"
    ]
  },
  "model": "sonnet",
  "enableAllProjectMcpServers": true,
  "statusLine": {
    "type": "command",
    "command": "python3 /media/sam/1TB/claude-hooks-shared/scripts/context-monitor.py",
    "env": {
      "CLAUDE_PROJECT_NAME": "PROJECT_NAME_PLACEHOLDER"
    }
  },
  "env": {
    "USE_BUILTIN_RIPGREP": "1",
    "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1",
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "0",
    "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
    "DISABLE_COST_WARNINGS": "1"
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/core/context_bundle_builder.py",
            "env": {
              "CLAUDE_PROJECT_NAME": "PROJECT_NAME_PLACEHOLDER"
            }
          }
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "tdd-guard"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/safety/smart-safety-check.py",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/safety/git-safety-check.py",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "WebSearch",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"import json, sys, re; from datetime import datetime; input_data = json.load(sys.stdin); tool_input = input_data.get('tool_input', {}); query = tool_input.get('query', ''); current_year = str(datetime.now().year); has_year = re.search(r'\\\\b20\\\\d{2}\\\\b', query); has_temporal = any(word in query.lower() for word in ['latest', 'recent', 'current', 'new', 'now', 'today']); should_add_year = not has_year and not has_temporal; modified_query = f'{query} {current_year}' if should_add_year else query; output = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'modifiedToolInput': {'query': modified_query}}}; print(json.dumps(output)); sys.exit(0)\"",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/core/post-tool-use.py",
            "env": {
              "CLAUDE_PROJECT_NAME": "PROJECT_NAME_PLACEHOLDER"
            }
          }
        ]
      },
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/productivity/auto-format.py",
            "timeout": 10
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/ux/notification.py",
            "env": {
              "ENGINEER_NAME": "Sam"
            }
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/ux/stop.py"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/productivity/subagent-checkpoint.sh"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "tdd-guard"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [
          {
            "type": "command",
            "command": "tdd-guard"
          }
        ]
      }
    ]
  }
}
EOF

# Replace project name placeholder
sed -i "s/PROJECT_NAME_PLACEHOLDER/$PROJECT_NAME/g" "$PROJECT_PATH/.claude/settings.local.json"

# 5. Setup TDD guard if requested
if [[ "$TDD_GUARD" == true ]]; then
  echo -e "${YELLOW}🛡️  Configuring TDD guard...${NC}"

  # Copy TDD guard instructions
  cp /media/sam/1TB/UTXOracle/.claude/tdd-guard/data/instructions.md "$PROJECT_PATH/.claude/tdd-guard/data/"

  # Create .tddguard.json
  cat > "$PROJECT_PATH/.tddguard.json" <<EOF
{
  "coverage_threshold": 80,
  "enforce_red_green_refactor": true,
  "baby_steps_mode": true,
  "max_attempts": 3,
  "exclude_patterns": [
    "tests/**",
    "scripts/**",
    ".claude/**"
  ]
}
EOF

  echo -e "${GREEN}✅ TDD guard configured (coverage: 80%)${NC}"
fi

# 6. Generate agents
if [[ -n "$AGENTS" ]]; then
  echo -e "${YELLOW}👥 Generating agents...${NC}"
  IFS=',' read -ra AGENT_LIST <<< "$AGENTS"
  for agent in "${AGENT_LIST[@]}"; do
    agent_file="$PROJECT_PATH/.claude/agents/${agent}.md"

    # Check if template exists in claude-hooks-shared
    template_path="$CLAUDE_HOOKS_SHARED/templates/agents/${agent}.md"
    if [[ -f "$template_path" ]]; then
      # Use existing template
      cp "$template_path" "$agent_file"
      echo -e "${GREEN}✅ Generated: ${agent}.md (from template)${NC}"
    else
      # Generate generic template
      cat > "$agent_file" <<EOF
# ${agent} Agent

**Role**: [Describe agent responsibility]

**Expertise**: [Domain knowledge]

**Responsibilities**:
- Define specific responsibilities
- Clarify scope and boundaries

**Tasks**:
- Task 1: [Description]
- Task 2: [Description]
- Task 3: [Description]

**Tools**:
- Read, Write, Edit (code implementation)
- Bash (run commands, test code)
- mcp__serena (navigate codebase)
- WebSearch (research best practices)

**Workflow**:
1. Understand requirements
2. Plan implementation (use TodoWrite)
3. Execute with TDD (Red-Green-Refactor)
4. Test and validate
5. Document decisions

**Communication**:
- Ask clarifying questions early
- Show progress with TodoWrite
- Report blockers within 3 attempts
- Share intermediate results

**TDD Approach**:
- Write failing test first (RED)
- Implement minimal code to pass (GREEN)
- Refactor with tests passing (REFACTOR)
- Never skip test coverage

**Common Pitfalls to Avoid**:
- ❌ Premature optimization
- ❌ Over-engineering
- ❌ Skipping tests
- ❌ Ignoring error handling
EOF

      echo -e "${GREEN}✅ Generated: ${agent}.md (generic template)${NC}"
    fi
  done
fi

# 7. Create pyproject.toml (UV template)
echo -e "${YELLOW}📦 Generating pyproject.toml...${NC}"
cat > "$PROJECT_PATH/pyproject.toml" <<EOF
[project]
name = "$(echo $PROJECT_NAME | tr '[:upper:]' '[:lower:]')"
version = "0.1.0"
description = "Claude Code project: $PROJECT_NAME"
requires-python = ">=3.11"
dependencies = [
    "duckdb>=0.9.0",
    "fastapi>=0.104.0",
    "redis>=5.0.0",
    "pydantic>=2.5.0",
    "plotly>=5.17.0",
    "uvicorn>=0.24.0",
    "websockets>=12.0",
    "pandas>=2.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "--cov=src --cov-report=term-missing --cov-report=html"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
ignore = []
EOF

# 8. Create .python-version
echo "3.11" > "$PROJECT_PATH/.python-version"

# 9. Create .gitignore
echo -e "${YELLOW}📝 Generating .gitignore...${NC}"
cat > "$PROJECT_PATH/.gitignore" <<'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/

# IDEs
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# Data (IMPORTANT: Don't commit processed data)
data/processed/
data/cache/
*.duckdb
*.duckdb.wal
*.rdb

# Environment
.env
.env.local

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db

# Serena/Specify cache
.serena/cache/
.specify/memory/

# Backups
*.backup
*.bak
EOF

# 10. Create .env.example
cat > "$PROJECT_PATH/.env.example" <<'EOF'
# Redis configuration
REDIS_URL=redis://localhost:6379/0

# API configuration
API_HOST=0.0.0.0
API_PORT=8000

# Data paths (adjust as needed)
DATA_RAW_PATH=data/raw
DATA_PROCESSED_PATH=data/processed

# Binance API (if using real-time streaming)
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
EOF

# 11. Generate CLAUDE.md from template
echo -e "${YELLOW}📝 Generating CLAUDE.md...${NC}"
if [[ -f "$CLAUDE_HOOKS_SHARED/templates/CLAUDE.md.template" ]]; then
  cp "$CLAUDE_HOOKS_SHARED/templates/CLAUDE.md.template" "$PROJECT_PATH/CLAUDE.md"

  # Replace placeholders
  sed -i "s/PROJECT_NAME/$PROJECT_NAME/g" "$PROJECT_PATH/CLAUDE.md"
  sed -i "s/\[PROJECT_DESCRIPTION\]/Add project description here/g" "$PROJECT_PATH/CLAUDE.md"
  sed -i "s/\[ARCHITECTURE_DESCRIPTION\]/Add architecture overview here/g" "$PROJECT_PATH/CLAUDE.md"
  sed -i "s/\[AGENT_LIST\]/See .claude\/agents\/ directory for agent specifications/g" "$PROJECT_PATH/CLAUDE.md"
  sed -i "s/\[LICENSE_INFO\]/Add license information here/g" "$PROJECT_PATH/CLAUDE.md"

  echo -e "${GREEN}✅ Generated: CLAUDE.md${NC}"
else
  echo -e "${RED}⚠️  Template not found: $CLAUDE_HOOKS_SHARED/templates/CLAUDE.md.template${NC}"
fi

# Generate README.md from template
echo -e "${YELLOW}📝 Generating README.md...${NC}"
if [[ -f "$CLAUDE_HOOKS_SHARED/templates/README.md.template" ]]; then
  cp "$CLAUDE_HOOKS_SHARED/templates/README.md.template" "$PROJECT_PATH/README.md"
  sed -i "s/PROJECT_NAME/$PROJECT_NAME/g" "$PROJECT_PATH/README.md"
  echo -e "${GREEN}✅ Generated: README.md${NC}"
fi

# 13. Link data source if provided
if [[ -n "$DATA_SOURCE" && -d "$DATA_SOURCE" ]]; then
  echo -e "${YELLOW}🔗 Linking data source...${NC}"
  ln -sf "$DATA_SOURCE" "$PROJECT_PATH/data/raw"
  echo -e "${GREEN}✅ Linked: data/raw/ → $DATA_SOURCE${NC}"
else
  echo -e "${YELLOW}⚠️  No data source provided. Create data/raw/ symlink manually.${NC}"
fi

# 14. Initialize git repository
echo -e "${YELLOW}🔧 Initializing git repository...${NC}"
cd "$PROJECT_PATH"
git init
git add .
git commit -m "Initial commit: Project setup via new-project.sh

🤖 Generated with claude-hooks-shared/scripts/new-project.sh
Co-Authored-By: Claude <noreply@anthropic.com>"

echo ""
echo -e "${GREEN}✅ Project created successfully!${NC}"
echo ""
echo -e "${GREEN}📊 Summary:${NC}"
echo "  Project: $PROJECT_NAME"
echo "  Path: $PROJECT_PATH"
if [[ -n "$DATA_SOURCE" ]]; then
  echo "  Data: $DATA_SOURCE"
fi
if [[ "$TDD_GUARD" == true ]]; then
  echo "  TDD Guard: Enabled (coverage: 80%)"
fi
if [[ -n "$AGENTS" ]]; then
  echo "  Agents: $AGENTS"
fi
echo ""
echo -e "${YELLOW}📝 Next steps:${NC}"
echo "  1. cd $PROJECT_PATH"
echo "  2. uv sync  # Install dependencies"
echo "  3. uv run pytest  # Verify TDD setup"
echo "  4. Edit CLAUDE.md to customize project instructions"
echo ""
