# Claude Hooks Shared - Templates

This directory contains reusable templates for bootstrapping new Claude Code projects.

## Templates

### `CLAUDE.md.template`
**Purpose**: Project instructions template with best practices
**Variables**:
- `PROJECT_NAME` - Project name (auto-replaced)
- `[PROJECT_DESCRIPTION]` - Short project overview (manual edit)
- `[ARCHITECTURE_DESCRIPTION]` - Architecture overview (manual edit)
- `[AGENT_LIST]` - List of agents (auto-generated if agents provided)
- `[LICENSE_INFO]` - License information (manual edit)

### `agents/`
**Purpose**: Specialized agent templates for common roles

**Available**:
- `data-engineer.md` - Data ingestion, DuckDB, ETL pipelines
- `quant-analyst.md` - Liquidation modeling, heatmaps, backtesting

**Usage**: Automatically copied when using `--agents` flag in `new-project.sh`

## Usage

### Create New Project

```bash
/media/sam/1TB/claude-hooks-shared/scripts/new-project.sh \
  --name "LiquidationHeatmap" \
  --path "/media/sam/1TB" \
  --data-source "/media/sam/3TB-WDC/binance-history-data-downloader/downloads/BTCUSDT" \
  --agents "data-engineer,quant-analyst" \
  --tdd-guard
```

### What Gets Created

```
ProjectName/
├── CLAUDE.md              # From CLAUDE.md.template (placeholders replaced)
├── .claude/
│   ├── agents/            # From templates/agents/ (if --agents specified)
│   ├── skills/            # Generic skills (pytest, pydantic, github)
│   ├── commands/          # SpecKit commands
│   └── settings.local.json # Pre-configured hooks
├── data/
│   ├── raw/               # Symlink to --data-source
│   ├── processed/         # Empty (for DuckDB)
│   └── cache/             # Empty (for Redis)
├── pyproject.toml         # UV dependencies
├── .gitignore             # Ignore patterns
└── .tddguard.json         # TDD configuration (if --tdd-guard)
```

### Customizing Templates

1. **Edit existing template**: Modify files in `templates/`
2. **Add new agent template**: Create `templates/agents/your-agent.md`
3. **Test changes**: Run `new-project.sh` in test directory

### Template Best Practices

- **Keep CLAUDE.md concise**: 200-400 lines max
- **Use placeholders**: `[VARIABLE_NAME]` for manual edits
- **Auto-replace when possible**: Use `sed` in script for known values
- **Document assumptions**: Add comments explaining design decisions
- **Version templates**: Update when patterns change

## Template Maintenance

**When to update**:
- ✅ New best practice discovered (e.g., better TDD workflow)
- ✅ New dependency pattern (e.g., switching from pip to uv)
- ✅ New hook configuration (e.g., adding safety checks)
- ✅ New agent role identified (e.g., security-auditor)

**How to update**:
1. Edit template file
2. Test with `new-project.sh` in temp directory
3. Verify generated project structure
4. Document changes in this README
5. Update all existing projects (if breaking change)

## Examples

### Minimal Project (No Agents)

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

### Full-Stack Trading System

```bash
new-project.sh \
  --name "TradingBot" \
  --path "/media/sam/1TB" \
  --data-source "/data/exchange-feeds" \
  --agents "data-engineer,quant-analyst" \
  --tdd-guard
```
