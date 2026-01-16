# Cron Failure Runbook

## Diagnosis

### Check Cron Status
```bash
# View current crontab
crontab -l

# Check cron daemon
systemctl status cron

# Check cron logs
grep CRON /var/log/syslog | tail -50
```

### Check Job Logs
```bash
# Weekly health report
tail -50 /tmp/claude-hooks/weekly_health_report.log

# Rotation checker
tail -50 /tmp/claude-hooks/rotation_checker.log
```

## Common Issues

### Job Not Running

1. **Cron daemon not running:**
   ```bash
   sudo systemctl start cron
   sudo systemctl enable cron
   ```

2. **Script not executable:**
   ```bash
   chmod +x /home/sam/.claude/scripts/*.sh
   chmod +x /media/sam/1TB/claude-hooks-shared/scripts/*.sh
   ```

3. **Path issues:**
   - Cron has minimal PATH
   - Use absolute paths in scripts
   - Add PATH at top of crontab

### SOPS Decryption Failing

```bash
# Verify age keys accessible
ls -la ~/.config/sops/age/keys.txt

# Test SOPS manually
SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt \
    sops -d /media/sam/1TB/claude-hooks-shared/.env.enc
```

### Discord Notification Failing

```bash
# Verify webhook exists in SOPS
sops -d /media/sam/1TB/claude-hooks-shared/.env.enc 2>/dev/null | \
    grep -q DISCORD_WEBHOOK_URL && echo "Webhook configured"
```

## Manual Run

```bash
# Run health report manually
/home/sam/.claude/scripts/weekly-health-report.sh

# Run rotation checker manually
/media/sam/1TB/claude-hooks-shared/scripts/rotation_checker.sh
```

## Heartbeat Check

```bash
# Check if automation is alive
python3 /media/sam/1TB/claude-hooks-shared/scripts/heartbeat.py status
```
