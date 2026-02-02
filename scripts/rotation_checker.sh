#!/bin/bash
#===============================================================================
# Secret Rotation Checker
#
# Cron job that checks if secret rotation is due and notifies via Discord.
# Does NOT automatically rotate - just sends reminder.
#
# Usage:
#   ./rotation_checker.sh                    # Check and notify if due
#   Add to crontab: 0 9 * * 1 /path/to/rotation_checker.sh
#
# Environment:
#   DISCORD_WEBHOOK_URL - Discord webhook for notifications
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROTATION_SCRIPT="$SCRIPT_DIR/secret_rotation.py"
DOTENVX="/home/sam/.local/bin/dotenvx"
ENV_FILE="/media/sam/1TB/.env"

# Load secrets from dotenvx (not from environment/crontab!)
if [[ -f "$ENV_FILE" ]]; then
    eval "$($DOTENVX decrypt -f "$ENV_FILE" --stdout 2>/dev/null | grep -E '^[A-Z_]+=' | sed 's/^/export /')"
fi

DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"

# Run rotation check
echo "Checking secret rotation status..."
if python3 "$ROTATION_SCRIPT" --check 2>&1; then
    echo "Rotation not due yet."
    exit 0
fi

# Rotation is due - send Discord notification
echo "Rotation is due! Sending notification..."

if [[ -z "$DISCORD_WEBHOOK_URL" ]]; then
    echo "WARNING: DISCORD_WEBHOOK_URL not set, skipping notification"
    exit 1
fi

# Get details
DAYS_OVERDUE=$(python3 -c "
import json
from pathlib import Path
from datetime import datetime

state_file = Path.home() / '.config/dotenvx/rotation_state.json'
if state_file.exists():
    state = json.load(open(state_file))
    last = datetime.fromisoformat(state.get('last_rotation', datetime.now().isoformat()))
    days = (datetime.now() - last).days
    overdue = days - 90
    print(overdue if overdue > 0 else 0)
else:
    print('N/A')
")

# Send Discord notification
curl -s -H "Content-Type: application/json" \
    -d "{
        \"embeds\": [{
            \"title\": \"🔐 Secret Rotation Due\",
            \"description\": \"It's time to rotate your dotenvx encryption keys.\",
            \"color\": 16744448,
            \"fields\": [
                {
                    \"name\": \"Days Overdue\",
                    \"value\": \"$DAYS_OVERDUE\",
                    \"inline\": true
                },
                {
                    \"name\": \"Action Required\",
                    \"value\": \"Run: \`python3 /media/sam/1TB/claude-hooks-shared/scripts/secret_rotation.py\`\",
                    \"inline\": false
                },
                {
                    \"name\": \"What it does\",
                    \"value\": \"• Runs dotenvx rotate\\n• Re-encrypts all .env files\\n• Creates backup before changes\",
                    \"inline\": false
                }
            ],
            \"footer\": {
                \"text\": \"Enterprise Secret Management\"
            },
            \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
        }]
    }" \
    "$DISCORD_WEBHOOK_URL"

echo "Notification sent!"
