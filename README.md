# TouchDesigner Python debug MCP

This project lets Cursor debug Python running inside TouchDesigner. A component in the TouchDesigner project executes code on the main thread. Cursor talks to that component through a local MCP server.

## One-time setup

From this repository:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Cursor loads the server from `.cursor/mcp.json` when this folder is the workspace.

## Install into the TouchDesigner startup project

TouchDesigner is already set to open this file on launch:

`/Users/mrwilson/Library/CloudStorage/Dropbox/vFX/TouchDesigner/Default.toe`

1. Open TouchDesigner so it loads `Default.toe`.
2. Open the Textport (Dialogs → Textport and DATs, or Alt+T) and run:

```python
exec(open("/Users/mrwilson/software/td-mcp/td_plugin/install.py").read(), globals())
```

3. Confirm the Textport reports `td-python-debug listening on 127.0.0.1:8765`.
4. Save `Default.toe` (Cmd+S). Startup File Mode is already Custom File for that path, so leave Preferences unchanged.
5. Quit TouchDesigner, open it again, and confirm the listen line appears without running the installer.
6. Reload this Cursor window so `.cursor/mcp.json` connects. `td_status` should report the TouchDesigner Python version.

The component is `/project1/td_python_debug`. Its Module Path parameter points at this repository, and Auto Start is on. Code changes in the repository apply the next time TouchDesigner launches. Re-run the installer if you want the saved callbacks themselves updated, then save `Default.toe` again.

The plugin listens on `127.0.0.1` only and requires the token in `~/.td-mcp/connection.json`. `execute_python` runs arbitrary Python inside TouchDesigner.

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
