# Secret Rotation Runbook

## Overview
SOPS/age encryption keys rotation every 90 days.

## When to Rotate
- Every 90 days (automated reminder via Discord)
- After suspected compromise
- When team member leaves

## Automated Rotation (Recommended)

```bash
# Check status
python3 /media/sam/1TB/claude-hooks-shared/scripts/secret_rotation.py --check

# Auto-rotate with notification
python3 /media/sam/1TB/claude-hooks-shared/scripts/secret_rotation.py --unattended --notify-discord
```

## Manual Rotation

```bash
# Interactive mode
python3 /media/sam/1TB/claude-hooks-shared/scripts/secret_rotation.py

# Follow prompts:
# 1. Backup current keys
# 2. Generate new age key
# 3. Re-encrypt all repos
# 4. Verify decryption works
# 5. Commit changes
```

## Rollback

If rotation fails:
```bash
# Restore from backup
cp ~/.config/sops/age/keys.txt.YYYYMMDD ~/.config/sops/age/keys.txt

# Restore .env.enc files from backup
# Backups at: /media/sam/2TB-NVMe/backups/secrets/pre_rotation_YYYYMMDD_HHMMSS/
```

## Repos Affected
- nautilus_dev
- UTXOracle
- N8N_dev
- LiquidationHeatmap
- backstage-portal
- academic_research
- claude-hooks-shared
- ~/.claude
