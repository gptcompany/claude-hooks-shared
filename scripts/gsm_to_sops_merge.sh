#!/bin/bash
#===============================================================================
# GSM to SOPS Merge Script
#
# Fetches latest HIGH-RISK secrets from Google Secret Manager and updates
# the encrypted .env.enc files for all repositories.
#
# Usage:
#   ./gsm_to_sops_merge.sh         # Merge all repos
#   ./gsm_to_sops_merge.sh --dry-run   # Show what would be updated
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - sops and age installed
#   - age keys in ~/.config/sops/age/keys.txt
#===============================================================================

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE ==="
fi

# Repositories to update
REPOS=(
    "/media/sam/1TB/nautilus_dev"
    "/media/sam/1TB/N8N_dev"
    "/media/sam/1TB/UTXOracle"
    "/media/sam/1TB/LiquidationHeatmap"
    "/media/sam/1TB/backstage-portal"
    "/media/sam/1TB/academic_research"
    "/media/sam/1TB/claude-hooks-shared"
    "$HOME/.claude"
)

# GSM Secret mappings: gsm_name -> env_var_name
declare -A GSM_SECRETS=(
    ["github-token"]="GITHUB_PAT"
    ["openai-api-key"]="OPENAI_API_KEY"
    ["gemini-api-key"]="GEMINI_API_KEY"
    ["discord-bot-token"]="DISCORD_TOKEN"
    ["sentry-auth-token"]="SENTRY_AUTH_TOKEN"
    ["grafana-service-token"]="GRAFANA_SERVICE_ACCOUNT_TOKEN"
    ["n8n-api-key"]="N8N_API_KEY"
    ["jwt-secret-key"]="JWT_SECRET"
    ["hyperliquid-testnet-pk"]="HYPERLIQUID_TESTNET_PK"
)

# Also update these aliases
declare -A GSM_ALIASES=(
    ["github-token"]="GITHUB_PERSONAL_ACCESS_TOKEN GITHUB_TOKEN"
)

echo "=== GSM to SOPS Merge Started: $(date) ==="

# Check prerequisites
if ! gcloud auth print-access-token &>/dev/null; then
    echo "ERROR: gcloud not authenticated. Run: gcloud auth login"
    exit 1
fi

if ! command -v sops &>/dev/null; then
    echo "ERROR: sops not found"
    exit 1
fi

# Get age public key for encryption
AGE_KEYS_FILE="$HOME/.config/sops/age/keys.txt"
if [[ ! -f "$AGE_KEYS_FILE" ]]; then
    echo "ERROR: age keys not found at $AGE_KEYS_FILE"
    exit 1
fi
AGE_PUBLIC_KEY=$(grep "public key" "$AGE_KEYS_FILE" | cut -d: -f2 | tr -d ' ')
echo "Using age public key: ${AGE_PUBLIC_KEY:0:20}..."

# Fetch all secrets from GSM
echo "Fetching secrets from Google Secret Manager..."
declare -A FETCHED_SECRETS

for gsm_name in "${!GSM_SECRETS[@]}"; do
    env_var="${GSM_SECRETS[$gsm_name]}"
    value=$(gcloud secrets versions access latest --secret="$gsm_name" 2>/dev/null || echo "")

    if [[ -n "$value" ]]; then
        FETCHED_SECRETS[$env_var]="$value"
        echo "  OK: $env_var from $gsm_name"

        # Handle aliases
        if [[ -v "GSM_ALIASES[$gsm_name]" ]]; then
            for alias in ${GSM_ALIASES[$gsm_name]}; do
                FETCHED_SECRETS[$alias]="$value"
                echo "  OK: $alias (alias)"
            done
        fi
    else
        echo "  SKIP: $gsm_name (not found)"
    fi
done

echo ""
echo "=== Updating repositories ==="

for repo in "${REPOS[@]}"; do
    repo_name=$(basename "$repo")
    env_enc="$repo/.env.enc"

    if [[ ! -f "$env_enc" ]]; then
        echo "SKIP: $repo_name (no .env.enc)"
        continue
    fi

    echo "Processing: $repo_name"

    # Decrypt current file
    current_env=$(sops -d --input-type dotenv --output-type dotenv "$env_enc" 2>/dev/null || echo "")

    if [[ -z "$current_env" ]]; then
        echo "  ERROR: Could not decrypt $env_enc"
        continue
    fi

    # Create temp file with updated values
    temp_env=$(mktemp)

    # Write current env vars, updating with GSM values
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ -z "$line" || "$line" =~ ^# ]]; then
            echo "$line" >> "$temp_env"
            continue
        fi

        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            old_value="${BASH_REMATCH[2]}"

            if [[ -v "FETCHED_SECRETS[$key]" ]]; then
                new_value="${FETCHED_SECRETS[$key]}"
                echo "$key=$new_value" >> "$temp_env"

                if [[ "$old_value" != "$new_value" ]]; then
                    echo "  UPDATED: $key"
                fi
            else
                echo "$line" >> "$temp_env"
            fi
        else
            echo "$line" >> "$temp_env"
        fi
    done <<< "$current_env"

    if [[ "$DRY_RUN" == true ]]; then
        echo "  (dry-run: would update $env_enc)"
        rm "$temp_env"
    else
        # Re-encrypt with SOPS using age key explicitly
        sops -e --age "$AGE_PUBLIC_KEY" --input-type dotenv --output-type dotenv "$temp_env" > "${env_enc}.new"
        mv "${env_enc}.new" "$env_enc"
        rm "$temp_env"
        echo "  OK: $env_enc updated"
    fi
done

echo ""
echo "=== Merge Complete ==="
