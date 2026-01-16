#!/bin/bash
set -euo pipefail

# Enterprise Template Sync v1.0
# Idempotent deployment of templates to repos
# Usage: sync_templates.sh [--force]

GLOBAL_TEMPLATES="$HOME/.claude/templates"
REPOS=(
  "/media/sam/1TB/nautilus_dev"
  "/media/sam/1TB/UTXOracle"
  "/media/sam/1TB/N8N_dev"
  "/media/sam/1TB/LiquidationHeatmap"
)

FORCE="${1:-}"

echo ""
echo "=============================================="
echo "  ENTERPRISE TEMPLATE SYNC"
echo "=============================================="
echo ""

# Check templates exist
if [[ ! -d "$GLOBAL_TEMPLATES" ]]; then
  echo "ERROR: Templates directory not found: $GLOBAL_TEMPLATES"
  exit 1
fi

# Backup function
backup_if_exists() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local backup="${file}.backup.$(date +%Y%m%d-%H%M%S)"
    cp "$file" "$backup"
    echo "    Backed up: $(basename "$backup")"
  fi
}

for repo in "${REPOS[@]}"; do
  name=$(basename "$repo")
  echo ""
  echo "-------------------------------------------"
  echo " Processing: $name"
  echo "-------------------------------------------"

  # Pre-commit config
  if [[ ! -f "$repo/.pre-commit-config.yaml" ]] || [[ "$FORCE" == "--force" ]]; then
    if [[ -f "$GLOBAL_TEMPLATES/.pre-commit-config.yaml" ]]; then
      backup_if_exists "$repo/.pre-commit-config.yaml"
      cp "$GLOBAL_TEMPLATES/.pre-commit-config.yaml" "$repo/"
      echo "  [+] Created .pre-commit-config.yaml"
    fi
  else
    echo "  [=] .pre-commit-config.yaml exists (skipped)"
  fi

  # MkDocs config
  if [[ ! -f "$repo/mkdocs.yml" ]] || [[ "$FORCE" == "--force" ]]; then
    if [[ -f "$GLOBAL_TEMPLATES/mkdocs.yml" ]]; then
      backup_if_exists "$repo/mkdocs.yml"
      sed "s/\${PROJECT_NAME}/$name/g" "$GLOBAL_TEMPLATES/mkdocs.yml" > "$repo/mkdocs.yml"

      # Create minimal docs structure
      mkdir -p "$repo/docs"
      mkdir -p "$repo/docs/api"
      mkdir -p "$repo/docs/runbooks"

      # Create index.md if missing
      if [[ ! -f "$repo/docs/index.md" ]]; then
        cat > "$repo/docs/index.md" << EOF
# $name Documentation

Welcome to the $name documentation.

## Quick Start

See [README](../README.md) for installation instructions.

## Architecture

See [ARCHITECTURE.md](../ARCHITECTURE.md) for system design.

## API Reference

See [API Reference](api/index.md) for API documentation.
EOF
        echo "  [+] Created docs/index.md"
      fi

      # Create api/index.md if missing
      if [[ ! -f "$repo/docs/api/index.md" ]]; then
        cat > "$repo/docs/api/index.md" << EOF
# API Reference

API documentation for $name.

## Endpoints

*Documentation to be added.*
EOF
        echo "  [+] Created docs/api/index.md"
      fi

      # Create runbooks/index.md if missing
      if [[ ! -f "$repo/docs/runbooks/index.md" ]]; then
        cat > "$repo/docs/runbooks/index.md" << EOF
# Runbooks

Operational runbooks for $name.

## Available Runbooks

*Runbooks to be added.*
EOF
        echo "  [+] Created docs/runbooks/index.md"
      fi

      echo "  [+] Created mkdocs.yml + docs/"
    fi
  else
    echo "  [=] mkdocs.yml exists (skipped)"
  fi

  # Validation config
  if [[ ! -f "$repo/.claude/validation/config.json" ]]; then
    if [[ -f "$GLOBAL_TEMPLATES/validation-config.json" ]]; then
      mkdir -p "$repo/.claude/validation"
      cp "$GLOBAL_TEMPLATES/validation-config.json" "$repo/.claude/validation/config.json"
      echo "  [+] Created .claude/validation/config.json"
    fi
  else
    echo "  [=] validation/config.json exists (skipped)"
  fi

  # ARCHITECTURE.md
  if [[ ! -f "$repo/ARCHITECTURE.md" ]] || [[ "$FORCE" == "--force" ]]; then
    if [[ -f "$GLOBAL_TEMPLATES/ARCHITECTURE.md" ]]; then
      backup_if_exists "$repo/ARCHITECTURE.md"
      sed "s/\${PROJECT_NAME}/$name/g" "$GLOBAL_TEMPLATES/ARCHITECTURE.md" > "$repo/ARCHITECTURE.md"
      echo "  [+] Created ARCHITECTURE.md"
    fi
  else
    echo "  [=] ARCHITECTURE.md exists (skipped)"
  fi
done

echo ""
echo "=============================================="
echo "  SYNC COMPLETE"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. cd <repo> && pre-commit install"
echo "  2. pre-commit run --all-files"
echo "  3. git add . && git commit -m 'chore: add enterprise templates'"
echo ""
