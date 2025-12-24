# UX Notification Hooks

Centralized notification logic for Claude Code.

## Hooks

### `notification.py` (Notification hook)
**Trigger**: When Claude sends a notification
**Purpose**: **Unified voice + desktop notifications** for urgent user actions

**Sends BOTH (voice + desktop) for**:
- `needs your input` → "Your agent needs your input!"
- `requires approval` → "A tool requires your approval"
- `waiting for confirmation` → "Subagent waiting for confirmation"
- `Task finished` → "Subagent task finished!"

**Silent for everything else**:
- Generic system notifications
- Informational messages
- Tool completions (not important enough)

**Voice**: `spd-say` (Linux) / `say` (macOS)
**Desktop**: `notify-send` (Linux) / `osascript` (macOS)

### `stop.py` (Stop hook)
**Trigger**: When user stops Claude
**Purpose**: Custom stop behavior (if needed)

## Design Principles

1. **Single source of truth**: All notification logic in `claude-hooks-shared`
2. **Fail-silent**: Never block Claude on notification errors
3. **Configurable**: Easy to adjust thresholds/filters
4. **Cross-platform**: Works on macOS + Linux

## Configuration

Used by projects via `.claude/settings.local.json`:
```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/media/sam/1TB/claude-hooks-shared/hooks/ux/notification.py",
            "env": {
              "ENGINEER_NAME": "Sam",
              "NAME_CHANCE": "0.7"
            }
          }
        ]
      }
    ]
  }
}
```

**Environment variables**:
- `ENGINEER_NAME`: Your name for personalized voice announcements (e.g., "Sam, your agent needs input")
- `NAME_CHANCE`: Probability (0.0-1.0) of including name in voice announcement (default: `0.7` = 70%)

**Note**: No PostToolUse hook needed! All notifications handled by `notification.py` hook only.

## Adjusting Filters

**Add new notification pattern** (sends both voice + desktop):
```python
# notification.py
notification_patterns = {
    "your new pattern": {
        "title": "Desktop Title",
        "message": "Desktop notification text (detailed)",
        "voice": "Voice announcement text (concise)"
    }
}
```

## Testing

```bash
# Test notification hook (voice + desktop)
echo '{"message": "Your agent needs your input"}' | ./notification.py

# Should trigger BOTH:
# - Desktop: "Your agent needs your input!"
# - Voice: "Your agent needs your input"
```
