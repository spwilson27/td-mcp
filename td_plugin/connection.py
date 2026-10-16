"""Shared connection file written for the Cursor MCP process."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def connection_path() -> Path:
    override = os.environ.get("TD_MCP_CONNECTION")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".td-mcp" / "connection.json"


def write_connection(
    port: int,
    token: str,
    host: str = DEFAULT_HOST,
    path: Path | None = None,
) -> Path:
    dest = path or connection_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {"host": host, "port": int(port), "token": token}
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(dest, 0o600)
    return dest
