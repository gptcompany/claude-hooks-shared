# New Project Setup - Summary

## ✅ Script Created

**Location**: `/media/sam/1TB/claude-hooks-shared/scripts/new-project.sh`

**Features**:
- ✅ Copy `.claude/` configuration (generic skills, commands, TDD guard)
- ✅ Generate `settings.local.json` (pre-configured hooks)
- ✅ Setup TDD guard (80% coverage threshold)
- ✅ Generate agents from templates (data-engineer, quant-analyst)
- ✅ Create `pyproject.toml` (DuckDB, FastAPI, Redis deps)
- ✅ Generate `CLAUDE.md` (best practices, concise)
- ✅ Generate `README.md` (quick start guide)
- ✅ Symlink data source (read-only access)
- ✅ Initialize git repository

## 📦 Templates Created

### 1. `CLAUDE.md.template`
**Size**: ~350 lines (concise, focused on best practices)
**Sections**:
- Project Overview
- Architecture (3-layer: data, API, frontend)
- Development Principles (KISS, YAGNI, Code Reuse)
- TDD Workflow (Red-Green-Refactor)
- Agent & Skill Architecture
- Task Completion Protocol

**Placeholders**:
- `PROJECT_NAME` (auto-replaced)
- `[PROJECT_DESCRIPTION]` (manual edit)
- `[ARCHITECTURE_DESCRIPTION]` (manual edit)
- `[AGENT_LIST]` (auto-generated)
- `[LICENSE_INFO]` (manual edit)

### 2. `agents/data-engineer.md`
**Purpose**: Data ingestion, DuckDB optimization, ETL pipelines
**Key Sections**:
- Role & Expertise
- Responsibilities & Tasks
- TDD Approach
- Common Pitfalls
- Example Task

### 3. `agents/quant-analyst.md`
**Purpose**: Liquidation modeling, heatmap algorithms, backtesting
**Key Sections**:
- Role & Expertise
- Liquidation Formulas (Binance long/short)
- Model Validation Checklist
- Existing Models to Leverage (py-liquidation-map)
- Common Pitfalls

### 4. `README.md.template`
**Purpose**: Public-facing project documentation
**Size**: ~80 lines
**Sections**:
- Quick Start
- Architecture
- Development (setup, testing, TDD)
- Project Structure
- Contributing

## 🎯 LiquidationHeatmap Project Created

**Location**: `/media/sam/1TB/LiquidationHeatmap`

**Structure**:
```
LiquidationHeatmap/
├── .claude/
│   ├── agents/
│   │   ├── data-engineer.md       # DuckDB, ETL specialist
│   │   └── quant-analyst.md       # Liquidation modeling specialist
│   ├── skills/                    # 3 generic skills (pytest, pydantic, github)
│   ├── commands/                  # SpecKit (8 slash commands)
│   ├── settings.local.json        # Pre-configured hooks
│   └── tdd-guard/                 # TDD enforcement (80% coverage)
├── data/
│   ├── raw/ → symlink to Binance CSV (3TB-WDC)
│   ├── processed/                 # Empty (for DuckDB)
│   └── cache/                     # Empty (for Redis)
├── src/                           # Empty (ready for code)
├── tests/                         # Empty (ready for tests)
├── scripts/                       # Empty (ready for batch jobs)
├── frontend/                      # Empty (ready for visualizations)
├── CLAUDE.md                      # Development guide (350 lines)
├── README.md                      # Public docs (80 lines)
├── pyproject.toml                 # UV dependencies (DuckDB, FastAPI, Redis)
├── .tddguard.json                 # TDD configuration
├── .gitignore                     # Ignore processed/, cache/, *.duckdb
└── .env.example                   # Environment template
```

**Data Source**: Symlinked to `/media/sam/3TB-WDC/binance-history-data-downloader/downloads/BTCUSDT`
- ✅ trades/
- ✅ bookDepth/
- ✅ fundingRate/
- ✅ klines/
- ✅ metrics/ (Open Interest)

**Dependencies** (pyproject.toml):
- duckdb>=0.9.0
- fastapi>=0.104.0
- redis>=5.0.0
- pydantic>=2.5.0
- plotly>=5.17.0
- uvicorn>=0.24.0
- websockets>=12.0
- pandas>=2.1.0

**Dev Dependencies**:
- pytest>=7.4.0
- pytest-asyncio>=0.21.0
- pytest-cov>=4.1.0 (coverage reporting)
- ruff>=0.1.0 (linting/formatting)

## 🚀 Next Steps

### 1. Setup Dependencies
```bash
cd /media/sam/1TB/LiquidationHeatmap
uv sync  # Install dependencies (fast!)
```

### 2. Customize CLAUDE.md
Edit placeholders:
- `[PROJECT_DESCRIPTION]` → "Calculate liquidation heatmaps from Binance futures data"
- `[ARCHITECTURE_DESCRIPTION]` → Add 3-layer architecture details
- `[LICENSE_INFO]` → Add license (MIT, Apache, etc.)

### 3. Start Development
**Option A**: Use Claude Code with new project
```bash
# Open in Claude Code (switch to LiquidationHeatmap project)
# Claude will read CLAUDE.md automatically
```

**Option B**: Manual development
```bash
# Create first feature with TDD
uv run pytest  # Should pass (no tests yet)
touch tests/test_ingestion.py
# Write failing test → RED
# Implement minimal code → GREEN
# Refactor → REFACTOR
```

## 📊 Script Usage Examples

### Minimal Project (No Agents, No Data)
```bash
new-project.sh --name "SimpleAPI" --path "/tmp"
```

### Data Science Project
```bash
new-project.sh \
  --name "MLPipeline" \
  --path "/media/sam/1TB" \
  --agents "data-engineer" \
  --tdd-guard
```

### Full-Stack with Real-Time Data
```bash
new-project.sh \
  --name "TradingBot" \
  --path "/media/sam/1TB" \
  --data-source "/data/exchange-feeds" \
  --agents "data-engineer,quant-analyst" \
  --tdd-guard
```

## 🎓 Design Decisions

### Why DuckDB?
- ✅ Zero-copy CSV ingestion (10GB in 5 seconds)
- ✅ In-process (no server to manage)
- ✅ Fast analytics (vectorized queries)
- ✅ Single file backup (copy .duckdb = full backup)

### Why Symlink Raw Data?
- ✅ Separation of concerns (raw vs processed)
- ✅ Immutable source (team can't overwrite CSV)
- ✅ Single source of truth (DuckDB for queries)
- ✅ Portable (copy processed/*.duckdb = deploy)

### Why TDD Guard?
- ✅ Enforces test-first discipline
- ✅ 80% coverage threshold (adjustable)
- ✅ Baby steps mode (minimal implementations)
- ✅ Max 3 attempts (prevents infinite loops)

### Why UV (not pip)?
- ✅ 10-100x faster than pip
- ✅ Deterministic lockfile (uv.lock)
- ✅ Auto-creates venv
- ✅ Compatible with pyproject.toml

## 🔄 Template Updates

**When to update templates**:
- New best practice discovered
- New dependency pattern (e.g., new MCP tool)
- New hook configuration
- New agent role identified

**How to update**:
1. Edit template in `/media/sam/1TB/claude-hooks-shared/templates/`
2. Test with `new-project.sh` in `/tmp`
3. Document changes in templates/README.md
4. (Optional) Update existing projects

## 📝 Files Created

1. `/media/sam/1TB/claude-hooks-shared/scripts/new-project.sh` (executable)
2. `/media/sam/1TB/claude-hooks-shared/templates/CLAUDE.md.template`
3. `/media/sam/1TB/claude-hooks-shared/templates/README.md.template`
4. `/media/sam/1TB/claude-hooks-shared/templates/agents/data-engineer.md`
5. `/media/sam/1TB/claude-hooks-shared/templates/agents/quant-analyst.md`
6. `/media/sam/1TB/claude-hooks-shared/templates/README.md` (documentation)
7. `/media/sam/1TB/LiquidationHeatmap/` (full project structure)

## ✅ Completion Checklist

- [x] Script created and tested
- [x] CLAUDE.md template (concise, ~350 lines)
- [x] Agent templates (data-engineer, quant-analyst)
- [x] TDD guard configuration
- [x] README.md template
- [x] LiquidationHeatmap project created
- [x] Data symlinked (Binance CSV)
- [x] Git initialized
- [ ] Dependencies installed (run `uv sync`)
- [ ] CLAUDE.md placeholders filled
- [ ] First feature implemented (TDD workflow)

## 🎯 Success Criteria

✅ **Script runs successfully** → Tested in /tmp
✅ **Project structure correct** → 29 files created
✅ **Data symlink works** → Points to Binance CSV
✅ **TDD guard configured** → .tddguard.json exists
✅ **Agents copied** → data-engineer.md, quant-analyst.md
✅ **CLAUDE.md concise** → ~350 lines (not beefy)
✅ **Dependencies defined** → pyproject.toml ready for `uv sync`

## 🚀 Ready to Start!

```bash
cd /media/sam/1TB/LiquidationHeatmap
uv sync
# Start coding with Claude Code or manually
```
