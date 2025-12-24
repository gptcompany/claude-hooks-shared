#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

import json
import sys
import subprocess
import random
import os
import platform


def send_notification(title: str, message: str, voice_message: str = None):
    """
    Send both desktop and voice notification.

    Args:
        title: Desktop notification title
        message: Desktop notification message (full detail)
        voice_message: Voice announcement (if None, uses message)
    """
    system = platform.system().lower()

    # Desktop notification
    try:
        if system == "darwin":  # macOS
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{message}" with title "{title}"',
                ],
                capture_output=True,
                timeout=5,
            )
        elif system == "linux":  # Linux (Ubuntu, etc.)
            subprocess.run(
                ["notify-send", title, message], capture_output=True, timeout=5
            )
    except Exception:
        pass  # Fail silently

    # Voice announcement
    try:
        # Get engineer name if available
        engineer_name = os.getenv("ENGINEER_NAME", "").strip()
        name_chance = float(os.getenv("NAME_CHANCE", "0.7"))  # 70% default

        # Use custom voice message or default to desktop message
        voice_text = voice_message or message

        # Personalize with engineer name (configurable probability)
        if (
            engineer_name
            and random.random() < name_chance
            and "your" in voice_text.lower()
        ):
            voice_text = voice_text.replace("your", f"{engineer_name}, your").replace(
                "Your", f"{engineer_name}, your"
            )

        if system == "darwin":  # macOS
            subprocess.run(
                ["say", "-v", "Samantha", voice_text], capture_output=True, timeout=10
            )
        elif system == "linux":  # Linux (Ubuntu, etc.)
            subprocess.run(
                ["spd-say", "-t", "female1", voice_text],
                capture_output=True,
                timeout=10,
            )
    except Exception:
        pass  # Fail silently


def main():
    try:
        # Read JSON input from stdin
        input_data = json.loads(sys.stdin.read())
        message = input_data.get("message", "")

        # Whitelist of notification patterns requiring user attention
        notification_patterns = {
            "needs your input": {
                "title": "Claude Code",
                "message": "Your agent needs your input!",
                "voice": "Your agent needs your input",
            },
            "requires approval": {
                "title": "Claude Code - Approval Required",
                "message": "A tool requires your approval",
                "voice": "A tool requires your approval",
            },
            "waiting for confirmation": {
                "title": "Claude Code - Confirmation",
                "message": "Subagent waiting for confirmation",
                "voice": "Subagent waiting for confirmation",
            },
            "Task finished": {
                "title": "Claude Code - Task Complete",
                "message": "Subagent task finished!",
                "voice": "Task finished",
            },
        }

        # Check if message matches any pattern
        for pattern, notification_config in notification_patterns.items():
            if pattern.lower() in message.lower():
                send_notification(
                    title=notification_config["title"],
                    message=notification_config["message"],
                    voice_message=notification_config["voice"],
                )
                break

        sys.exit(0)

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
