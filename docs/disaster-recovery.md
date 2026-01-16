# Disaster Recovery Plan

**Version**: 1.0
**Last Updated**: 2026-01-16
**Owner**: Infrastructure Team

---

## Overview

This document outlines the disaster recovery procedures for the enterprise infrastructure stack, including secrets management, databases, and core services.

## Recovery Priority

| Priority | Service | RTO | RPO |
|----------|---------|-----|-----|
| P1 - Critical | SOPS/age Keys | 15 min | 0 (encrypted backups) |
| P1 - Critical | PostgreSQL | 30 min | 1 hour |
| P2 - High | QuestDB | 1 hour | 4 hours |
| P2 - High | Redis | 1 hour | 1 hour |
| P3 - Medium | N8N Workflows | 2 hours | 24 hours |
| P3 - Medium | Backstage | 2 hours | 24 hours |
| P4 - Low | Grafana Dashboards | 4 hours | 24 hours |

---

## 1. Secrets Recovery

### Backup Location
```
/media/sam/2TB-NVMe/backups/secrets/
├── YYYYMMDD_HHMMSS/
│   ├── nautilus_dev.env.enc
│   ├── N8N_dev.env.enc
│   ├── UTXOracle.env.enc
│   ├── LiquidationHeatmap.env.enc
│   ├── backstage-portal.env.enc
│   ├── academic_research.env.enc
│   ├── claude-hooks-shared.env.enc
│   ├── .claude.env.enc
│   ├── age_keys.txt.age
│   └── MANIFEST.txt
```

### Recovery Procedure

#### Step 1: Recover age Keys
```bash
# If age keys are lost, decrypt from backup
# You need the recovery passphrase or another authorized key

# List available backups
ls -la /media/sam/2TB-NVMe/backups/secrets/

# Choose most recent backup
BACKUP_DIR="/media/sam/2TB-NVMe/backups/secrets/YYYYMMDD_HHMMSS"

# Decrypt age keys (requires original key or recovery key)
age -d -i ~/.config/sops/age/keys.txt $BACKUP_DIR/age_keys.txt.age > recovered_keys.txt

# Or if keys are completely lost, use offline recovery key
age -d -i /path/to/offline/recovery.key $BACKUP_DIR/age_keys.txt.age > recovered_keys.txt

# Restore keys
mkdir -p ~/.config/sops/age
mv recovered_keys.txt ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```

#### Step 2: Restore Encrypted Secrets
```bash
# Copy .env.enc files back to repositories
BACKUP_DIR="/media/sam/2TB-NVMe/backups/secrets/YYYYMMDD_HHMMSS"

cp $BACKUP_DIR/nautilus_dev.env.enc /media/sam/1TB/nautilus_dev/.env.enc
cp $BACKUP_DIR/N8N_dev.env.enc /media/sam/1TB/N8N_dev/.env.enc
cp $BACKUP_DIR/UTXOracle.env.enc /media/sam/1TB/UTXOracle/.env.enc
cp $BACKUP_DIR/LiquidationHeatmap.env.enc /media/sam/1TB/LiquidationHeatmap/.env.enc
cp $BACKUP_DIR/backstage-portal.env.enc /media/sam/1TB/backstage-portal/.env.enc
cp $BACKUP_DIR/academic_research.env.enc /media/sam/1TB/academic_research/.env.enc
cp $BACKUP_DIR/claude-hooks-shared.env.enc /media/sam/1TB/claude-hooks-shared/.env.enc
cp $BACKUP_DIR/.claude.env.enc ~/.claude/.env.enc
```

#### Step 3: Verify Decryption
```bash
# Test decryption for each repository
for repo in nautilus_dev N8N_dev UTXOracle LiquidationHeatmap backstage-portal academic_research claude-hooks-shared; do
    echo "Testing $repo..."
    sops -d --input-type dotenv --output-type dotenv /media/sam/1TB/$repo/.env.enc > /dev/null && echo "OK" || echo "FAIL"
done
```

---

## 2. Database Recovery

### QuestDB
```bash
# Location: /var/lib/questdb or Docker volume questdb-data

# Stop QuestDB
docker stop questdb

# Restore from backup (if using Docker)
docker run --rm -v questdb-data:/data -v /path/to/backup:/backup alpine \
    tar xzf /backup/questdb-backup.tar.gz -C /data

# Start QuestDB
docker start questdb

# Verify
curl http://localhost:9000/exec?query=SELECT%20count()%20FROM%20trading_pnl
```

### Redis
```bash
# Stop Redis
docker stop redis

# Restore RDB snapshot
cp /path/to/backup/dump.rdb /var/lib/redis/dump.rdb

# Start Redis
docker start redis

# Verify
redis-cli ping
```

### PostgreSQL (if applicable)
```bash
# Restore from pg_dump
pg_restore -h localhost -U postgres -d dbname /path/to/backup.dump
```

---

## 3. Service Recovery

### Priority Order
1. **Databases first**: QuestDB, Redis, PostgreSQL
2. **Core infrastructure**: Prometheus, Alertmanager
3. **Monitoring**: Grafana, Loki
4. **Applications**: N8N, UTXOracle, Backstage

### Docker Compose Recovery
```bash
# Start all services in order
cd /media/sam/1TB/nautilus_dev
docker-compose -f docker-compose.staging.yml up -d

# Or for production
cd /media/sam/2TB-NVMe/prod
docker-compose up -d
```

### Systemd Services Recovery
```bash
# Restart all infrastructure services
sudo systemctl restart prometheus alertmanager grafana-server

# Verify
systemctl status prometheus alertmanager grafana-server
```

---

## 4. Cloudflare Tunnel Recovery

### If cloudflared service fails
```bash
# Check status
systemctl status cloudflared

# View logs
journalctl -u cloudflared -n 50

# Restart
sudo systemctl restart cloudflared

# If credentials are lost, re-authenticate
cloudflared tunnel login
cloudflared tunnel route dns n8n-tunnel n8nubuntu.princyx.xyz
```

### Tunnel Configuration
```
Location: ~/.cloudflared/config.yml
Credentials: ~/.cloudflared/*.json
```

---

## 5. Full System Recovery Checklist

```markdown
## Pre-Recovery
- [ ] Identify failure scope (partial vs full)
- [ ] Locate most recent backup
- [ ] Verify backup integrity

## Infrastructure
- [ ] Recover age keys
- [ ] Restore .env.enc files
- [ ] Verify SOPS decryption works

## Databases
- [ ] Restore QuestDB
- [ ] Restore Redis
- [ ] Verify data integrity

## Services
- [ ] Start Docker containers
- [ ] Start systemd services
- [ ] Verify Cloudflare tunnel

## Monitoring
- [ ] Verify Prometheus scraping
- [ ] Verify Grafana dashboards
- [ ] Verify Alertmanager rules

## Applications
- [ ] Test N8N workflows
- [ ] Test Backstage catalog
- [ ] Test UTXOracle API

## Final Verification
- [ ] Run health check script
- [ ] Verify all endpoints accessible
- [ ] Check for alerts
```

---

## 6. Contact Information

| Role | Contact |
|------|---------|
| Infrastructure Lead | @sam |
| On-call | Discord #alerts |

---

## 7. Backup Schedule

| What | When | Retention |
|------|------|-----------|
| Secrets (.env.enc) | Daily 2 AM | 30 days |
| QuestDB | Daily 3 AM | 7 days |
| Redis RDB | Every 1 hour | 24 hours |
| Grafana | Weekly | 4 weeks |

---

## 8. Testing Schedule

| Test | Frequency |
|------|-----------|
| Secrets decryption | Weekly (automated) |
| Backup restore drill | Monthly |
| Full DR drill | Quarterly |

---

## 9. Key Rotation

### Automatic Rotation Schedule
- **Interval**: Every 90 days
- **Check**: Weekly (Monday 9 AM via cron)
- **Notification**: Discord alert when rotation is due

### Manual Rotation
```bash
# Check rotation status
python3 /media/sam/1TB/claude-hooks-shared/scripts/secret_rotation.py --check

# Perform rotation (interactive, with confirmation)
python3 /media/sam/1TB/claude-hooks-shared/scripts/secret_rotation.py

# Force rotation (no prompts - use with caution)
python3 /media/sam/1TB/claude-hooks-shared/scripts/secret_rotation.py --force
```

### What Rotation Does
1. Creates pre-rotation backup
2. Generates new age keypair
3. Decrypts all .env.enc with old key
4. Re-encrypts all with new key
5. Verifies all new encryptions
6. Commits changes atomically
7. Updates .sops.yaml config
8. Archives old key

### Rotation State
```
Location: ~/.config/sops/age/rotation_state.json
Contains: last_rotation, rotation_count, previous_key_archive
```

---

## Appendix: Emergency Commands

```bash
# Quick health check
/media/sam/1TB/claude-hooks-shared/scripts/backup_secrets.sh

# Decrypt all secrets (verify keys work)
for f in /media/sam/1TB/*/.env.enc; do
    sops -d --input-type dotenv --output-type dotenv "$f" > /dev/null && echo "OK: $f" || echo "FAIL: $f"
done

# Check all containers
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check systemd services
systemctl list-units --type=service --state=running | grep -E "prometheus|grafana|alert|cloudflare"
```
