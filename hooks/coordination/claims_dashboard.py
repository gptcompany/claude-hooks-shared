#!/usr/bin/env python3
"""Claims Dashboard - Visual display of all claims across agents.

Standalone utility that displays the current claims board in a formatted table.
Reads from ~/.claude-flow/claims/claims.json (same file as MCP server).

Usage:
  python3 claims_dashboard.py              # Display formatted dashboard
  python3 claims_dashboard.py --json       # Output raw JSON
  python3 claims_dashboard.py --watch      # Auto-refresh every 5s
  python3 claims_dashboard.py --watch -i 10  # Custom interval
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BOX_H, BOX_V, BOX_DH = "\u2500", "\u2502", "\u2550"
BOX_TL, BOX_TR, BOX_BL, BOX_BR = "\u250c", "\u2510", "\u2514", "\u2518"
DISPLAY_WIDTH = 60
CLAIMS_STORE_FILE = Path.home() / ".claude-flow" / "claims" / "claims.json"


def load_claims_store() -> dict:
    """Load claims store from file, creating if needed."""
    CLAIMS_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    default = {"claims": {}, "stealable": {}, "contests": {}}
    if not CLAIMS_STORE_FILE.exists():
        CLAIMS_STORE_FILE.write_text(json.dumps(default))
        return default
    try:
        data = json.loads(CLAIMS_STORE_FILE.read_text())
        return {k: data.get(k, {}) for k in default}
    except Exception:
        return default


def normalize_claimant(claimant) -> str:
    """Convert claimant to string format."""
    if isinstance(claimant, dict):
        return f"{claimant.get('type', '')}:{claimant.get('agentId', '')}:{claimant.get('agentType', '')}"
    return str(claimant) if claimant else "unknown"


def format_time_ago(timestamp: str) -> str:
    """Format timestamp as relative time."""
    if not timestamp:
        return "unknown"
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
        if seconds < 60:
            return f"{seconds} seconds ago"
        if seconds < 3600:
            m = seconds // 60
            return f"{m} minute{'s' if m != 1 else ''} ago"
        if seconds < 86400:
            h = seconds // 3600
            return f"{h} hour{'s' if h != 1 else ''} ago"
        d = seconds // 86400
        return f"{d} day{'s' if d != 1 else ''} ago"
    except Exception:
        return "unknown"


def get_claims_board() -> dict:
    """Get claims board data organized by status."""
    store = load_claims_store()
    extra_fields = ["stealReason", "stealContext", "markedStealableAt", "availableFor"]

    def to_claim_list(items: dict, status: str, include_extra: bool = False) -> list:
        result = []
        for issue_id, claim in items.items():
            entry = {
                "issueId": issue_id,
                "claimant": normalize_claimant(claim.get("claimant")),
                "status": status if status else claim.get("status", "active"),
                "claimedAt": claim.get("claimedAt"),
                "progress": claim.get("progress", 0),
            }
            if include_extra:
                for field in extra_fields:
                    if claim.get(field):
                        entry[field] = claim[field]
            result.append(entry)
        return result

    active = to_claim_list(store["claims"], None)
    stealable = to_claim_list(store["stealable"], "stealable", include_extra=True)

    return {
        "active": active,
        "stealable": stealable,
        "completed": [],
        "contests": list(store["contests"].values()),
        "stats": {
            "active": len(active),
            "stealable": len(stealable),
            "contests": len(store["contests"]),
        },
    }


def format_dashboard(data: dict, width: int = DISPLAY_WIDTH) -> str:
    """Format the full claims dashboard."""
    title_bar = BOX_DH * width

    def box_line(content: str, pos: str = "middle") -> str:
        if pos == "top":
            return BOX_TL + BOX_H * (width - 2) + BOX_TR
        if pos == "bottom":
            return BOX_BL + BOX_H * (width - 2) + BOX_BR
        return BOX_V + " " + content[: width - 4].ljust(width - 4) + " " + BOX_V

    def format_claim_box(claim: dict) -> list:
        lines = [box_line("", "top")]
        lines.append(
            box_line(
                claim.get("issueId", claim.get("issue_id", "unknown"))[: width - 6]
            )
        )
        claimant = normalize_claimant(claim.get("claimant", claim.get("owner")))
        lines.append(box_line(f"Claimed by: {claimant[: width - 18]}"))
        if claimed_at := claim.get("claimedAt", claim.get("claimed_at")):
            lines.append(box_line(f"Since: {format_time_ago(claimed_at)}"))
        if (progress := claim.get("progress")) is not None:
            lines.append(box_line(f"Progress: {progress}%"))
        if reason := claim.get("stealReason", claim.get("reason")):
            lines.append(box_line(f"Reason: {reason}"))
        if available := claim.get("availableFor", claim.get("available_for")):
            lines.append(box_line(f"Available for: {available}"))
        lines.append(box_line("", "bottom"))
        return lines

    lines = [title_bar, "CLAIMS DASHBOARD".center(width), title_bar, ""]

    if error := data.get("error"):
        return "\n".join(lines + [f"Error: {error}", "", title_bar])
    if raw := data.get("raw"):
        return "\n".join(lines + ["Raw output from claude-flow:", raw, "", title_bar])

    for section, label in [("active", "ACTIVE"), ("stealable", "STEALABLE")]:
        items = data.get(section, [])
        lines.append(f"{label} ({len(items)}):")
        if items:
            for claim in items:
                lines.extend(format_claim_box(claim))
        else:
            lines.append("  (none)")
        lines.append("")

    active_count = len(data.get("active", []))
    stealable_count = len(data.get("stealable", []))
    completed_count = len(data.get("completed", [])) or data.get("stats", {}).get(
        "completed", 0
    )
    lines.append(
        f"Summary: {active_count} active, {stealable_count} stealable, {completed_count} completed"
    )
    lines.append(title_bar)

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Claims Dashboard - display claims board"
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument(
        "--watch", "-w", action="store_true", help="Watch mode - refresh periodically"
    )
    parser.add_argument(
        "--interval", "-i", type=int, default=5, help="Refresh interval in seconds"
    )
    parser.add_argument(
        "--width", type=int, default=DISPLAY_WIDTH, help="Display width"
    )
    args = parser.parse_args()

    def display():
        data = get_claims_board()
        return (
            json.dumps(data, indent=2)
            if args.json
            else format_dashboard(data, args.width)
        )

    if args.watch:
        try:
            while True:
                # nosec B605 - command is hardcoded, no injection risk
                os.system("clear" if os.name != "nt" else "cls")  # nosec
                print(display())
                print(f"\nRefreshing every {args.interval}s... (Ctrl+C to stop)")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
        return 0

    print(display())
    return 0


if __name__ == "__main__":
    sys.exit(main())
