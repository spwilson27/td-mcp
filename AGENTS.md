# AGENTS.md (td-mcp)

Rules for AI coding agents working in this repo. Human docs: README.md, DEVELOPMENT.md.

## What this is
MCP server (`src/td_mcp`) + a TouchDesigner component (`td_plugin/`, shipped as the self-contained `tox/td_python_debug.tox`). Tools forward over loopback HTTP to the main thread inside TouchDesigner.

## Commands
- Tests: `.venv/bin/python -m pytest -q` (no TouchDesigner needed; must pass before every commit).
- Setup: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- Rebuild the tox: `.venv/bin/python scripts/build_tox.py` (launches its OWN scratch TouchDesigner).

## Rules
- **Rebuild the tox whenever `td_plugin/*.py` or the callbacks text in `td_plugin/install.py` change**, and commit `tox/td_python_debug.tox` and `tox/td_python_debug.manifest.json` together with the source. `tests/test_tox_manifest.py` fails on a stale tox. Then tell the user that `td-raster-editor/tests/td/` holds a copy that needs refreshing (copy both files; do not do it unasked in another repo).
- **Never touch the user's open TouchDesigner project.** Do not save, close or modify it; do not use `build_tox.py --attach` or `execute_python` against the user's TD to change anything unless asked. Prefer the default scratch-instance mode. Only kill TD processes you launched yourself; never the instance on port 8765 that the user is running.
- `execute_python` runs arbitrary code in TouchDesigner. Use read-only expressions when probing. Never change project `cookRate` or `time.play`.
- Wrap anything that talks to TD in a timeout; never `sleep` inside TD (it blocks the main thread and every request).
- Tokens (the connection file, the Token parameter) must never appear in commits, docs, logs or chat. The tox is built with a blank token; verify it stays blank.
- No machine-specific absolute paths in sources, docs, or the tox (use `<path-to-td-mcp>` placeholders). `/Users/` in embedded sources fails the manifest test.
- Loopback only: the server must keep rejecting non-loopback hosts.
- Stage explicit paths (`git add <file> ...`); never `git commit -a`. Do not push or tag unless the user explicitly asks.

## Environment variables
`TD_MCP_PORT` (override Port parameter), `TD_MCP_CONNECTION` (connection file path, shared by plugin and client), `TD_MCP_MODULEPATH` (directory containing `td_plugin/` when Module Path is empty), `TD_MCP_HOME` (checkout path for the installer), `TD_MCP_PYTHON` (interpreter for the debugpy pip hint), `TD_BIN` (TouchDesigner executable for `build_tox.py`).

## Key files
| File | Role |
|---|---|
| `src/td_mcp/server.py` | MCP tool definitions (one per handler) |
| `src/td_mcp/client.py` | connection file loading, HTTP call, error mapping |
| `td_plugin/runtime.py` | loopback HTTP hub, auth, main-thread job queue, port override |
| `td_plugin/handlers.py` | tool implementations + `_METHODS` registry |
| `td_plugin/context.py` | all `td` module access, debugpy, TD python lookup |
| `td_plugin/install.py` | `build_component`, callbacks text, source hashing |
| `scripts/build_tox.py` | tox + manifest builder |
| `tests/test_tox_manifest.py` | staleness guard |

## Recovery
If a TD you launched hangs (no response, `/health` times out): kill only that PID (`kill <pid>`; check with `ps` that it is yours), delete its temporary connection file, and relaunch. If the user's TD does not respond, report it; do not kill it.
