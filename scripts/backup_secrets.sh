#!/bin/bash
#===============================================================================
# Enterprise Secrets Backup Script
#
# Backs up all dotenvx .env + .env.keys files across repositories.
#
# Usage:
#   ./backup_secrets.sh
#   Add to crontab: 0 2 * * * /media/sam/1TB/claude-hooks-shared/scripts/backup_secrets.sh
#
# Retention: 30 days (configurable via RETENTION_DAYS)
#
# MIGRATION (2026-02-02): SOPS → dotenvx
#===============================================================================

set -euo pipefail

# Configuration
BACKUP_ROOT="/media/sam/2TB-NVMe/backups/secrets"
RETENTION_DAYS=30

# Directories containing dotenvx .env + .env.keys
DIRS=(
    "/media/sam/1TB"
    "/media/sam/1TB/N8N_dev"
    "/media/sam/1TB/backstage-portal"
    "/media/sam/1TB/hummingbot_scraper"
    "/media/sam/1TB/n_backup"
)

# Create timestamped backup directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

echo "=== Secrets Backup Started: $(date) ==="
echo "Backup directory: $BACKUP_DIR"

# Backup .env and .env.keys from each directory
for dir in "${DIRS[@]}"; do
    dir_name=$(basename "$dir")
    [[ "$dir" == "/media/sam/1TB" ]] && dir_name="SSOT-master"

    for file in .env .env.keys; do
        src="$dir/$file"
        if [[ -f "$src" ]]; then
            cp "$src" "$BACKUP_DIR/${dir_name}${file}"
            echo "OK: ${dir_name}/${file}"
        fi
    done
done

# Create manifest
cat > "$BACKUP_DIR/MANIFEST.txt" << EOF
Backup Timestamp: $TIMESTAMP
Backup Date: $(date)
Hostname: $(hostname)
User: $(whoami)
Tool: dotenvx (ECIES encryption)

Files:
$(ls -la "$BACKUP_DIR")

Recovery Instructions:
1. Copy .env and .env.keys back to original directory
2. Verify: dotenvx get GITHUB_PAT -f /media/sam/1TB/.env
3. dotenvx auto-decrypts using .env.keys in same directory
EOF

echo "OK: Manifest created"

# Cleanup old backups
if [[ -d "$BACKUP_ROOT" ]]; then
    echo "Cleaning up backups older than $RETENTION_DAYS days..."
    find "$BACKUP_ROOT" -maxdepth 1 -type d -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true
fi

BACKUP_COUNT=$(find "$BACKUP_ROOT" -maxdepth 1 -type d | wc -l)
echo "=== Backup Complete: $BACKUP_COUNT total backups retained ==="
