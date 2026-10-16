# TouchDesigner Python debug MCP

This project lets Cursor debug Python running inside TouchDesigner. A component in the TouchDesigner project executes code on the main thread. Cursor talks to that component through a local MCP server.

## One-time setup

From this repository:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Cursor loads the server from `.cursor/mcp.json` when this folder is the workspace (it uses `${workspaceFolder}/.venv/bin/python`; on Windows use `.venv\\Scripts\\python.exe`).

## Install into a TouchDesigner project

Preferred: drag `tox/td_python_debug.tox` into your project (any COMP, e.g. `/project1`) and save the project. The tox is self-contained: the `td_plugin` modules are embedded as DATs, so TouchDesigner needs no checkout of this repository. Token is blank and is generated at first start; Port is 8765 (override with the `TD_MCP_PORT` environment variable); Auto Start is on. The Textport reports `td-python-debug listening on 127.0.0.1:8765`.

Where `td_plugin` is loaded from (first match wins):

1. the component's **Module Path** parameter, when not empty (development: live code from a checkout, applied the next TouchDesigner launch);
2. the `TD_MCP_MODULEPATH` environment variable;
3. the modules embedded in the component.

### Development install (live code from this checkout)

Open the Textport (Dialogs → Textport and DATs, or Alt+T) and run, with the real path:

```python
p = "<path-to-td-mcp>/td_plugin/install.py"; exec(compile(open(p).read(), p, "exec"), {**globals(), "__file__": p})
```

(or set `TD_MCP_HOME=<path-to-td-mcp>` in the environment and run `exec(open("<path-to-td-mcp>/td_plugin/install.py").read(), globals())`). This creates `/project1/td_python_debug` with Module Path pointing at the checkout; save the project afterwards.

### Rebuilding the tox

After changing `td_plugin/*.py` or the callbacks in `td_plugin/install.py`, regenerate it:

```bash
.venv/bin/python scripts/build_tox.py
```

This launches its own scratch TouchDesigner (never touching an open project; `TD_BIN` selects the executable, otherwise the standard install locations are searched), saves `tox/td_python_debug.tox`, writes `tox/td_python_debug.manifest.json` (sha256 per embedded DAT) and re-opens the tox to check it runs from the embedded code alone. `pytest` fails when the manifest no longer matches the sources. `--attach` builds in a temporary COMP of the TouchDesigner in the connection file instead.

The plugin listens on `127.0.0.1` only and requires the token in `~/.td-mcp/connection.json` (override the location with `TD_MCP_CONNECTION`). `execute_python` runs arbitrary Python inside TouchDesigner.

If a tool times out, TouchDesigner is probably stopped on a dialog or the network is not cooking.

## Breakpoints

`start_debugpy` listens on `127.0.0.1:5678` and does not pause TouchDesigner. The first call returns a pip command when `debugpy` is not installed in TouchDesigner's Python. After installing it, attach with a Python debug configuration:

```json
{
  "name": "Attach to TouchDesigner",
  "type": "debugpy",
  "request": "attach",
  "connect": {"host": "127.0.0.1", "port": 5678}
}
```

## Tools

- `td_status` — connection, TouchDesigner version, and Python version
- `execute_python` — run code on the main thread and capture stdout plus any traceback
- `read_dat` / `write_dat` — inspect and replace script DAT text
- `list_python_dats` — find Python DATs under a path
- `operator_errors` — errors, warnings, and script errors
- `describe_operator` — type, errors, and parameters
- `start_debugpy` — listen for a debugger without waiting for a client
