# Development

## Layout

```
src/td_mcp/          MCP server side (runs in the MCP client's Python, not in TouchDesigner)
  server.py          MCPServer "td-python-debug"; one @mcp.tool per debug tool, each forwards to client.call()
  client.py          loads the connection file, POSTs JSON to http://127.0.0.1:PORT/rpc, maps errors to {"ok": false, "error": ...}
  __main__.py        `python -m td_mcp` (also the `td-mcp` console script)
td_plugin/           runs INSIDE TouchDesigner (embedded in the tox as DATs)
  runtime.py         Hub: ThreadingHTTPServer on loopback, job queue pumped on the main thread, bearer auth, /health, /rpc
  handlers.py        dispatch() and one function per tool (execute_python, read_dat, ...)
  context.py         TouchDesignerContext: the only place that touches the `td` module (faked in tests)
  connection.py      writes ~/.td-mcp/connection.json (TD_MCP_CONNECTION overrides)
  install.py         build_component() creates the COMP + DATs + callbacks; install() = dev install from a checkout
  web_paint*.py      unrelated Web Render paint demo (not in the tox)
scripts/build_tox.py builds tox/td_python_debug.tox and its manifest
tox/                 committed build output: td_python_debug.tox + td_python_debug.manifest.json (sha256 per embedded DAT)
tests/               pytest, no TouchDesigner needed (the TD side is faked)
```

## Architecture

```
 MCP client (Claude Code / Cursor)
        | stdio (MCP)
        v
 td_mcp.server  --tool call-->  td_mcp.client.call()
                                   | reads ~/.td-mcp/connection.json  {host, port, token}
                                   | HTTP POST /rpc  {"method", "params", "timeout"}   Authorization: Bearer <token>
                                   v                                        (127.0.0.1 only)
 TouchDesigner process
   td_python_debug COMP
     HTTP thread (daemon)  --enqueue Job-->  Queue
     Execute DAT onFrameStart  --Hub.pump()-->  handlers.dispatch()  on the MAIN thread
     HTTP thread waits on job.event (timeout -> HTTP 504) and returns {"result": ...}
```

Why a queue: TouchDesigner objects may only be touched from the main thread, so HTTP handler threads never call `td` directly. The Execute DAT (`callbacks`) drains the queue every frame; a blocked main thread or a modal dialog therefore shows up as a timeout.

How the component gets its code: the `bootstrap` DAT resolves `td_plugin` from (1) the Module Path parameter, (2) `TD_MCP_MODULEPATH`, (3) embedded `mod_*` DATs via an import hook. The embedded DATs are plain copies of `td_plugin/*.py`.

HTTP API of the component: `GET /health` (no auth), `POST /rpc` (auth). Errors are `{"error": {"message": ...}}` with 400/401/404/500/504.

## Dev setup

```bash
git clone <repo-url> td-mcp && cd td-mcp
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q          # 41 tests, a few seconds, no TouchDesigner required
```

## Edit, build, test loop

- Change `src/td_mcp/*`: takes effect the next time the MCP client launches the server (editable install). Restart the client's MCP server.
- Change `td_plugin/*.py` or the callbacks in `td_plugin/install.py`:
  1. For quick iteration use the installer (README, "installer script") so Module Path points at the checkout.
  2. Before committing, rebuild the shipped tox: `.venv/bin/python scripts/build_tox.py`.
  3. Run `.venv/bin/python -m pytest -q`.
- Adding a tool: add a function in `handlers.py` and register it in the `_METHODS` table near the bottom, add a `@mcp.tool()` in `server.py`, extend `tests/test_handlers.py` and the expected tool list in `tests/test_server.py`, rebuild the tox.

### Rebuilding the tox

```bash
.venv/bin/python scripts/build_tox.py                    # own scratch TouchDesigner, seeded from tox/td_python_debug.tox
.venv/bin/python scripts/build_tox.py --seed other.tox   # first build or broken tox
.venv/bin/python scripts/build_tox.py --attach           # temporary COMP in the TD from the connection file
```

Default mode launches a private TouchDesigner (own port and connection file) and kills it afterwards; an open project is never touched. `TD_BIN` selects the executable, otherwise standard install locations are searched. It saves the tox with a blank Token, writes the manifest and reopens the tox to check it works from the embedded code alone. `--attach` is the alternative when launching a second TD is not possible; it builds in a temp COMP and destroys it again.

## Tests

| Layer | Command | Notes |
|---|---|---|
| Unit (all) | `.venv/bin/python -m pytest -q` | No TD needed. |
| Manifest | `tests/test_tox_manifest.py` | Fails with "tox/ is stale" if embedded sources changed and the tox was not rebuilt; also checks the bootstrap import hook and that no `/Users/` paths are embedded. |
| Env overrides | `tests/test_env_overrides.py` | `TD_MCP_PORT`, `TD_MCP_CONNECTION`. |

There is no automated live-TD test; `build_tox.py` doubles as the live smoke test (it reopens the tox and calls it).

## Releasing / consumers

The tox is a build output committed to git. Downstream, `td-raster-editor` keeps a copy at `tests/td/td_python_debug.tox` (+ manifest) for its live validation tooling. After rebuilding the tox here, copy `tox/td_python_debug.tox` and `tox/td_python_debug.manifest.json` there and commit in that repo. Do not tag or push without being asked.

## Conventions

- Python 3.11+, `from __future__ import annotations`.
- `td_plugin/` must stay importable without TouchDesigner (everything touching `td` goes through `context.py` or a lazy `import td`).
- Never write machine-specific absolute paths into sources, docs or the tox (the manifest test scans embedded sources for `/Users/`).
- Tool results are always dicts; errors are `{"ok": false, "error": "..."}`.
