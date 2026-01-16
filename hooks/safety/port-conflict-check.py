#!/usr/bin/env python3
"""
Port Conflict Prevention Hook

Intercepts Bash commands that try to bind to ports and checks if:
1. Port is already in use
2. Port is reserved for a known service

Prevents orphan processes and port conflicts.
"""

import json
import re
import subprocess
import sys

# Reserved ports for known services (port -> service name)
RESERVED_PORTS = {
    3000: "grafana",
    3100: "loki",
    5432: "postgres",
    5433: "postgres-n8n",
    5678: "n8n",
    6379: "redis",
    7007: "backstage",
    8000: "utxoracle-api",
    8001: "utxoracle-ws",
    8080: "mempool-web",
    8086: "influxdb",
    8332: "bitcoind-rpc",
    8812: "questdb-pg",
    8999: "mempool-api",
    9000: "questdb-http",
    9009: "questdb-ilp",
    9090: "prometheus",
    9093: "alertmanager",
    9100: "node-exporter",
    11434: "ollama",
}


def is_port_in_use(port: int) -> tuple[bool, str | None]:
    """Check if port is in use and return process info."""
    try:
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.stdout.strip() and "LISTEN" in result.stdout:
            # Extract process name
            match = re.search(r'users:\(\("([^"]+)"', result.stdout)
            process = match.group(1) if match else "unknown"
            return True, process
    except Exception:
        pass
    return False, None


def extract_port_from_command(command: str) -> int | None:
    """Extract port number from common patterns."""
    patterns = [
        r"-m\s+http\.server\s+(\d+)",  # python -m http.server PORT
        r"--port[=\s]+(\d+)",  # --port=PORT or --port PORT
        r"-p[=\s]+(\d+)",  # -p=PORT or -p PORT (short form)
        r":(\d+)(?:\s|$|/)",  # :PORT in URLs or binds
        r"uvicorn.*--port[=\s]+(\d+)",  # uvicorn --port
        r"gunicorn.*-b[=\s]+[^:]+:(\d+)",  # gunicorn -b host:port
        r"flask.*--port[=\s]+(\d+)",  # flask --port
        r"node.*--port[=\s]+(\d+)",  # node --port
        r"npm.*PORT=(\d+)",  # PORT env var
    ]

    for pattern in patterns:
        match = re.search(pattern, command)
        if match:
            return int(match.group(1))
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")

        # Skip if not a server/bind command
        server_indicators = [
            "http.server",
            "--port",
            "-p ",
            "uvicorn",
            "gunicorn",
            "flask run",
            "npm start",
            "node ",
            "--bind",
            "listen",
        ]

        if not any(ind in command for ind in server_indicators):
            # Not a server command, allow
            print(json.dumps({}))
            sys.exit(0)

        port = extract_port_from_command(command)
        if not port:
            print(json.dumps({}))
            sys.exit(0)

        # Check if port is reserved
        if port in RESERVED_PORTS:
            service = RESERVED_PORTS[port]
            in_use, process = is_port_in_use(port)

            if in_use:
                output = {
                    "decision": "block",
                    "reason": f"Port {port} is reserved for '{service}' and currently in use by '{process}'. "
                    f"Use a different port or stop the existing service first.",
                }
                print(json.dumps(output))
                sys.exit(0)

        # Check if port is in use by anything
        in_use, process = is_port_in_use(port)
        if in_use:
            output = {
                "decision": "block",
                "reason": f"Port {port} is already in use by '{process}'. "
                f"Use a different port or stop the existing process: kill $(lsof -t -i:{port})",
            }
            print(json.dumps(output))
            sys.exit(0)

        # Port is free, allow
        print(json.dumps({}))
        sys.exit(0)

    except Exception:
        # On error, allow (fail open)
        print(json.dumps({}))
        sys.exit(0)


if __name__ == "__main__":
    main()
