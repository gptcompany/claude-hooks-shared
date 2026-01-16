# Hook Failure Runbook

## Diagnosis

### Check Hook Status
```bash
# List all hooks
ls -la /media/sam/1TB/claude-hooks-shared/hooks/

# Check permissions
find /media/sam/1TB/claude-hooks-shared/hooks/ -type f -name "*.py" ! -perm -u+x

# Test specific hook
python3 /media/sam/1TB/claude-hooks-shared/hooks/<category>/<hook>.py --help
```

### Check Logs
```bash
# Recent hook logs
tail -100 /tmp/claude-hooks/*.log

# Specific hook errors
grep -i error /tmp/claude-hooks/*.log
```

## Common Issues

### Python Import Error
```bash
# Check virtual environment
which python3
pip list | grep -E "(pyyaml|requests)"

# Install missing dependencies
pip install pyyaml requests
```

### Permission Denied
```bash
# Fix permissions
chmod +x /media/sam/1TB/claude-hooks-shared/hooks/**/*.py
```

### Hook Not Triggering
1. Check `~/.claude/settings.json` hooks configuration
2. Verify hook path is correct
3. Check if hook category matches event

## Reset Hooks

```bash
# Backup current settings
cp ~/.claude/settings.json ~/.claude/settings.json.backup

# Re-register hooks
python3 /media/sam/1TB/claude-hooks-shared/scripts/register_hooks.py
```

## Contact
If hook issues persist, check:
- `/media/sam/1TB/claude-hooks-shared/README.md`
- Hook source code for specific error handling
