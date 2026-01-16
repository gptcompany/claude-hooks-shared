#!/bin/bash
#===============================================================================
# Enterprise Secrets Backup Script
#
# Backs up all .env.enc files across repositories to timestamped directory.
# Also backs up age keys (encrypted with age itself for safety).
#
# Usage:
#   ./backup_secrets.sh                 # Manual run
#   Add to crontab: 0 2 * * * /media/sam/1TB/claude-hooks-shared/scripts/backup_secrets.sh
#
# Retention: 30 days (configurable via RETENTION_DAYS)
#===============================================================================

set -euo pipefail

# Configuration
BACKUP_ROOT="/media/sam/2TB-NVMe/backups/secrets"
RETENTION_DAYS=30
AGE_KEYS_FILE="$HOME/.config/sops/age/keys.txt"

# Repositories to backup
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

# Create timestamped backup directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

echo "=== Secrets Backup Started: $(date) ==="
echo "Backup directory: $BACKUP_DIR"

# Backup .env.enc files from each repo
for repo in "${REPOS[@]}"; do
    repo_name=$(basename "$repo")
    env_enc="$repo/.env.enc"

    if [[ -f "$env_enc" ]]; then
        cp "$env_enc" "$BACKUP_DIR/${repo_name}.env.enc"
        echo "OK: $repo_name"
    else
        echo "SKIP: $repo_name (no .env.enc)"
    fi
done

# Backup age keys (self-encrypted for safety)
if [[ -f "$AGE_KEYS_FILE" ]]; then
    # Get public key from keys file
    AGE_PUBLIC=$(grep "public key" "$AGE_KEYS_FILE" | cut -d: -f2 | tr -d ' ')

    # Encrypt the keys file with itself
    age -r "$AGE_PUBLIC" -o "$BACKUP_DIR/age_keys.txt.age" "$AGE_KEYS_FILE"
    echo "OK: age keys (self-encrypted)"
fi

# Create manifest
cat > "$BACKUP_DIR/MANIFEST.txt" << EOF
Backup Timestamp: $TIMESTAMP
Backup Date: $(date)
Hostname: $(hostname)
User: $(whoami)

Files:
$(ls -la "$BACKUP_DIR")

Recovery Instructions:
1. To decrypt age keys: age -d -i <recovery_key> age_keys.txt.age > keys.txt
2. To restore secrets: cp <repo>.env.enc /media/sam/1TB/<repo>/.env.enc
3. SOPS will auto-decrypt using the age keys
EOF

echo "OK: Manifest created"

# Cleanup old backups
if [[ -d "$BACKUP_ROOT" ]]; then
    echo "Cleaning up backups older than $RETENTION_DAYS days..."
    find "$BACKUP_ROOT" -maxdepth 1 -type d -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true
fi

# Count total backups
BACKUP_COUNT=$(find "$BACKUP_ROOT" -maxdepth 1 -type d | wc -l)
echo "=== Backup Complete: $BACKUP_COUNT total backups retained ==="
