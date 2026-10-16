# td-mcp: TouchDesigner Python debug MCP

Debug and inspect Python running inside TouchDesigner from an MCP client (Claude Code, Cursor, or any stdio MCP client).

A small component (`td_python_debug`) lives in your TouchDesigner project and serves a loopback-only HTTP endpoint. Requests are executed on TouchDesigner's **main thread**. The MCP server in this repo (`python -m td_mcp`) forwards tool calls to it.

```
MCP client  <--stdio-->  td_mcp (this repo)  <--HTTP, 127.0.0.1, bearer token-->  td_python_debug COMP in TouchDesigner
```

## Features

- `execute_python`: run code on the main thread, get the expression result, stdout, stderr and any traceback.
- Read and replace script DAT text, find Python DATs, list operators with errors, describe an operator and its parameters.
- `start_debugpy`: open a debugpy listener inside TouchDesigner (does not pause the UI) for breakpoint debugging from VS Code / Cursor.
- Self-contained component: `tox/td_python_debug.tox` embeds its Python modules, so TouchDesigner needs no checkout of this repo.
- Per-instance overrides (port, connection file) so several TouchDesigner instances can be driven side by side.

## Requirements

- TouchDesigner (tested with 2025.32820 on macOS; a free non-commercial licence is enough).
- Python 3.11 or newer on the machine running the MCP client (`pyproject.toml` says `>=3.11`; the development venv uses 3.14).
- The `mcp` Python package (`>=2,<3`), installed automatically by `pip install -e .`.

## Install

### 1. Install the MCP server

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # ".[dev]" adds pytest; use "." for just the server
```

This also installs a `td-mcp` console script (`.venv/bin/td-mcp`), equivalent to `.venv/bin/python -m td_mcp`.

### 2. Install the component into TouchDesigner

Drag `tox/td_python_debug.tox` into your project network (any COMP, for example `/project1`) and save the project.

- Token: blank in the tox; generated at first start and stored in the parameter.
- Port: 8765 (override with the `TD_MCP_PORT` environment variable, see below).
- Auto Start: on. The Textport prints `td-python-debug listening on 127.0.0.1:8765`.
- Start / Stop pulse parameters restart or stop the server.

On start the component writes `~/.td-mcp/connection.json` (host, port, token; mode 0600). The MCP server reads it for every call, so nothing needs to be copied by hand.

Where `td_plugin` is loaded from (first match wins):

1. the component's **Module Path** parameter, when not empty (development: live code from a checkout, applied the next TouchDesigner launch);
2. the `TD_MCP_MODULEPATH` environment variable;
3. the modules embedded in the component.

#### Alternative: installer script (live code from a checkout)

Open the Textport (Dialogs > Textport and DATs, or Alt+T) and run, with the real path:

```python
p = "<path-to-td-mcp>/td_plugin/install.py"; exec(compile(open(p).read(), p, "exec"), {**globals(), "__file__": p})
```

or set `TD_MCP_HOME=<path-to-td-mcp>` in TouchDesigner's environment and run `exec(open("<path-to-td-mcp>/td_plugin/install.py").read(), globals())`. This creates `/project1/td_python_debug` with Module Path pointing at the checkout. Save the project afterwards.

### 3. Connect an MCP client

The entrypoint is `python -m td_mcp` (or the `td-mcp` script) using the venv from step 1. Use an absolute path to the venv's python.

**Claude Code**

```bash
claude mcp add td-python-debug -- <path-to-td-mcp>/.venv/bin/python -m td_mcp
```

or a project-level `.mcp.json`:

```json
{
  "mcpServers": {
    "td-python-debug": {
      "command": "<path-to-td-mcp>/.venv/bin/python",
      "args": ["-m", "td_mcp"]
    }
  }
}
```

**Cursor**: this repo ships `.cursor/mcp.json`, which Cursor loads when the repo is the workspace:

```json
{
  "mcpServers": {
    "td-python-debug": {
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "td_mcp"]
    }
  }
}
```

For other workspaces put the same block in `~/.cursor/mcp.json` with an absolute path. On Windows use `.venv\Scripts\python.exe`.

Pass environment variables to the MCP server through the client config (`env` in JSON, `-e KEY=value` for `claude mcp add`), for example `TD_MCP_CONNECTION` to select one TouchDesigner instance.

## Usage

Ask the client to call `td_status` first. It reports TouchDesigner's version, Python version and project. Then:

| Tool | Purpose |
|---|---|
| `td_status` | Connection, TouchDesigner version, Python version, project name/folder |
| `execute_python(code, timeout=30)` | Run code on the main thread; expressions return a result, statements return stdout; failures include a traceback. `timeout` (seconds, max 120) is how long to wait for the main thread; running code is not interrupted. |
| `read_dat(path)` / `write_dat(path, text)` | Read / replace the text of a DAT (`/project1/script1`) |
| `list_python_dats(path="/", max_depth=4, limit=50)` | Find Python DATs under a path |
| `operator_errors(path="/", max_depth=4, limit=50)` | Operators with errors, warnings or script errors |
| `describe_operator(path, parameter_limit=40)` | Type, errors and parameters of an operator |
| `start_debugpy(port=5678)` | Listen for a debugger on `127.0.0.1:port` without pausing TouchDesigner |

Code in `execute_python` sees `op`, `ops`, `parent`, `me` (the debug component), `project`, `app`, `ui`, `mod`, `ipar` and `td`.

### Breakpoints

`start_debugpy` listens on `127.0.0.1:5678`. The first call returns a pip command when `debugpy` is not installed in TouchDesigner's Python (set `TD_MCP_PYTHON` to override which interpreter the command names). After installing it, attach with:

```json
{
  "name": "Attach to TouchDesigner",
  "type": "debugpy",
  "request": "attach",
  "connect": {"host": "127.0.0.1", "port": 5678}
}
```

debugpy can only change ports after restarting TouchDesigner.

## Environment variables

| Variable | Read by | Meaning |
|---|---|---|
| `TD_MCP_PORT` | component (TD) | Overrides the Port parameter (0..65535). Invalid values are logged and ignored. |
| `TD_MCP_CONNECTION` | component and MCP client | Path of the connection file (default `~/.td-mcp/connection.json`). Use different files for different TD instances. |
| `TD_MCP_MODULEPATH` | component (TD) | Directory containing `td_plugin/`, used when the Module Path parameter is empty. |
| `TD_MCP_HOME` | installer | Checkout path for `td_plugin/install.py` when it cannot locate itself. |
| `TD_MCP_PYTHON` | component (TD) | Python interpreter named in the debugpy pip hint. |
| `TD_BIN` | `scripts/build_tox.py` | TouchDesigner executable used to rebuild the tox. |

## Security

- The server binds to `127.0.0.1` / `localhost` only; anything else is rejected.
- Every `/rpc` call needs `Authorization: Bearer <token>`. The token is random (32 bytes, urlsafe), stored in the component's Token parameter and in `connection.json` (mode 0600). Do not commit or share either; the tox ships with a blank token.
- **`execute_python` runs arbitrary Python inside TouchDesigner** with your user's permissions, and `write_dat` rewrites project code. Anything that can reach the MCP client can do that. Treat the token like a password.
- Saving a project stores the token with it. Clear the Token parameter before sharing a `.toe`.
- Request bodies are capped at 2 MB; `execute_python` code at 200,000 characters.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "No connection file at ..." | The component has not started. Open the project, check the Textport for `td-python-debug listening`, or pulse Start. Check `TD_MCP_CONNECTION` is the same for TD and the client. |
| "TouchDesigner is not reachable at 127.0.0.1:PORT" | TD is closed, port changed, or a stale connection file points to a dead instance. Restart or pulse Start to rewrite it. |
| Tool times out / HTTP 504 | The main thread is blocked (modal dialog, cooking stopped, long script). Requests are served from the frame loop, so TD must be cooking. |
| "failed to listen on 127.0.0.1:PORT" in the Textport | Port in use (another TD instance). Set `TD_MCP_PORT` or the Port parameter. |
| HTTP 401 "unauthorized" | The connection file token differs from the component's Token (for example two TD instances sharing one file). |
| debugpy not installed | Run the pip command returned by `start_debugpy` against TouchDesigner's Python. |

## Also in this repo

`web_paint/` and `td_plugin/web_paint*.py` are an older, separate Web Render TOP paint demo (installer: `td_plugin/web_paint_install.py`, default port 9876). It is not needed for debugging and is not covered by the tox.

See [DEVELOPMENT.md](DEVELOPMENT.md) for architecture, tests and rebuilding the tox, and [AGENTS.md](AGENTS.md) for rules for AI coding agents.
