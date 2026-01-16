# Disaster Recovery Runbook

## Priority Order
1. Age keys (without these, ALL secrets are lost)
2. SOPS config
3. .env.enc files

## Recovery Procedures

### Lost Age Keys

**If backup exists:**
```bash
# Restore from backup
cp /media/sam/2TB-NVMe/backups/secrets/keys.txt.backup ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```

**If no backup:**
- All encrypted secrets are UNRECOVERABLE
- Generate new keys and recreate all secrets manually

### Corrupted .env.enc Files

```bash
# Check backup location
ls -la /media/sam/2TB-NVMe/backups/secrets/

# Restore specific file
cp /media/sam/2TB-NVMe/backups/secrets/pre_rotation_LATEST/<repo>.env.enc \
   /media/sam/1TB/<repo>/.env.enc
```

### Verify Recovery

```bash
# Test decryption for all repos
for repo in nautilus_dev UTXOracle N8N_dev LiquidationHeatmap; do
    echo "Testing $repo..."
    sops -d /media/sam/1TB/$repo/.env.enc > /dev/null && echo "OK" || echo "FAILED"
done
```

## Backup Locations
- Age keys: `~/.config/sops/age/keys.txt.*` (dated backups)
- Secrets: `/media/sam/2TB-NVMe/backups/secrets/`
- Pre-rotation: `/media/sam/2TB-NVMe/backups/secrets/pre_rotation_*/`

## Prevention
- Automated backups run daily
- Secret rotation creates backup before changes
- Never delete old key files until verified
