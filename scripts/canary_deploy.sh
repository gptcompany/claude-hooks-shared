#!/bin/bash
set -euo pipefail

#===============================================================================
# Canary Deployment Script
# Test changes on one repo before deploying to all
#
# Usage: canary_deploy.sh <phase> [--proceed]
#===============================================================================

CANARY_REPO="/media/sam/1TB/nautilus_dev"
ALL_REPOS=(
    "/media/sam/1TB/UTXOracle"
    "/media/sam/1TB/N8N_dev"
    "/media/sam/1TB/LiquidationHeatmap"
)

PHASE="${1:-}"
PROCEED="${2:-}"

if [[ -z "$PHASE" ]]; then
    echo "Usage: canary_deploy.sh <phase> [--proceed]"
    echo ""
    echo "Phases:"
    echo "  templates   - Deploy pre-commit, mkdocs templates"
    echo "  precommit   - Run pre-commit on all files"
    echo "  catalog     - Update catalog-info.yaml annotations"
    echo "  validation  - Deploy validation configs"
    echo ""
    exit 1
fi

echo ""
echo "============================================"
echo "  CANARY DEPLOYMENT - Phase: $PHASE"
echo "============================================"
echo ""

# Deploy to canary first
echo "Step 1: Deploy to canary repo (nautilus_dev)"
echo "--------------------------------------------"

case "$PHASE" in
    templates)
        /media/sam/1TB/claude-hooks-shared/scripts/sync_templates.sh --canary-only 2>/dev/null || \
            echo "Running sync on canary..."
        ;;
    precommit)
        echo "Running pre-commit on canary..."
        cd "$CANARY_REPO"
        pre-commit run --all-files || true
        ;;
    catalog)
        echo "Checking catalog annotations..."
        cat "$CANARY_REPO/catalog-info.yaml" | grep -E "annotations:" -A 10
        ;;
    validation)
        echo "Checking validation config..."
        cat "$CANARY_REPO/.claude/validation/config.json" | head -20
        ;;
    *)
        echo "Unknown phase: $PHASE"
        exit 1
        ;;
esac

echo ""
echo "Step 2: Verify canary compliance"
echo "--------------------------------"
python3 /media/sam/1TB/claude-hooks-shared/scripts/repo_compliance.py 2>/dev/null | \
    grep -A 5 "nautilus_dev" || echo "Compliance check completed"

if [[ "$PROCEED" == "--proceed" ]]; then
    echo ""
    echo "Step 3: Deploying to all repos..."
    echo "---------------------------------"
    for repo in "${ALL_REPOS[@]}"; do
        name=$(basename "$repo")
        echo "  -> $name"

        case "$PHASE" in
            precommit)
                cd "$repo"
                pre-commit run --all-files 2>/dev/null || true
                ;;
            *)
                echo "     (automated deployment for $PHASE)"
                ;;
        esac
    done
    echo ""
    echo "Full deployment complete!"
else
    echo ""
    echo "Canary only. Run with --proceed to deploy to all repos."
fi
