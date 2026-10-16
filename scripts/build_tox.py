"""Build tox/td_python_debug.tox: the self-contained debug component (td_plugin modules embedded as DATs).

    python scripts/build_tox.py                       # scratch TouchDesigner instance, seeded from tox/td_python_debug.tox
    python scripts/build_tox.py --seed some.tox       # ... or from another td-mcp tox (first build / broken tox)
    python scripts/build_tox.py --attach              # build in a temp COMP of the TouchDesigner described by the connection file

Needs TouchDesigner (a free non-commercial licence is enough). The default mode launches its OWN TouchDesigner process (own port,
own connection file, killed afterwards): an open project is never touched. --attach builds in a temporary COMP of the running
instance instead (TD_MCP_CONNECTION / ~/.td-mcp/connection.json) and destroys it again; nothing else there changes.

The component is built by td_plugin/install.py (build_component), saved with a BLANK Token (generated at first start), and a
manifest of sha256 per embedded DAT is written next to it (tox/td_python_debug.manifest.json). tests/test_tox_manifest.py fails
when the sources changed and the tox was not rebuilt.

TD binary: $TD_BIN, else the standard install locations.
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from td_mcp.client import call, load_connection  # noqa: E402
from td_plugin.install import source_hashes  # noqa: E402

TOX = ROOT / "tox" / "td_python_debug.tox"
MANIFEST = ROOT / "tox" / "td_python_debug.manifest.json"
TEMP_NAME = "_tdmcp_build"


def find_td_binary() -> str:
    env = os.environ.get("TD_BIN")
    if env:
        if not os.path.exists(env):
            raise SystemExit(f"TD_BIN={env} does not exist")
        return env
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates += ["/Applications/TouchDesigner.app/Contents/MacOS/TouchDesigner"]
        candidates += sorted(glob.glob("/Applications/TouchDesigner*.app/Contents/MacOS/TouchDesigner"), reverse=True)
    elif sys.platform.startswith("win"):
        for base in filter(None, (os.environ.get("ProgramFiles"), r"C:\Program Files")):
            candidates += sorted(glob.glob(os.path.join(base, "Derivative", "TouchDesigner*", "bin", "TouchDesigner.exe")), reverse=True)
    for c in candidates:
        if os.path.exists(c):
            return c
    raise SystemExit("TouchDesigner not found: set TD_BIN to the TouchDesigner executable.")


def build_code(out: str) -> str:
    return f"""
import importlib.util, hashlib, td
spec = importlib.util.spec_from_file_location("td_plugin_install_lib", {str(ROOT / "td_plugin" / "install.py")!r})
inst = importlib.util.module_from_spec(spec)
inst.__file__ = {str(ROOT / "td_plugin" / "install.py")!r}
spec.loader.exec_module(inst)
holder = td.op('/').create(td.baseCOMP, {TEMP_NAME!r})   # temp parent: the component keeps its real name, nothing else is touched
comp = None
try:
    comp = inst.build_component(holder, {str(ROOT)!r}, module_path='', name='td_python_debug', start=False)
    want = inst.source_hashes({str(ROOT)!r})
    for name, h in want.items():
        got = hashlib.sha256(comp.op(name).text.replace('\\r\\n', '\\n').encode('utf-8')).hexdigest()
        assert got == h, 'DAT text mismatch: ' + name
    assert str(comp.par.Token.eval()) == '', 'Token must be blank'
    assert comp.par.Modulepath.eval() == '', 'Modulepath must be blank'
    assert int(comp.par.Port.eval()) == 8765 and bool(comp.par.Autostart.eval())
    comp.save({out!r})
    print('saved', {out!r}, sorted(c.name for c in comp.children))
finally:
    holder.destroy()
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_in_td(code: str, conn=None) -> dict:
    res = call("execute_python", {"code": code}, connection=conn, timeout=90)
    if not res.get("ok"):
        raise SystemExit("build failed in TouchDesigner: " + str(res.get("traceback") or res.get("error"))[-1500:])
    print(res.get("stdout", "").strip())
    return res


@contextlib.contextmanager
def scratch_td(seed: Path, live_modules: bool):
    """Launch our own TouchDesigner on `seed` (own port + connection file); yields the Connection; kills only that process group."""
    td_bin = find_td_binary()
    work = Path(tempfile.mkdtemp(prefix="td_mcp_build_"))
    conn_file = work / "connection.json"
    env = dict(os.environ, TD_MCP_PORT=str(free_port()), TD_MCP_CONNECTION=str(conn_file))
    env.pop("TD_MCP_MODULEPATH", None)
    if live_modules:
        env["TD_MCP_MODULEPATH"] = str(ROOT)   # a seed with a blank Module Path then runs this checkout's code
    kwargs = {"start_new_session": True} if hasattr(os, "killpg") else {}
    proc = subprocess.Popen([td_bin, str(seed)], env=env, stdout=open(work / "td.log", "w"), stderr=subprocess.STDOUT, **kwargs)
    try:
        deadline = time.time() + 150
        conn = None
        while time.time() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"scratch TouchDesigner exited early, see {work / 'td.log'}")
            if conn_file.exists():
                try:
                    conn = load_connection(conn_file)
                    break
                except Exception:
                    pass
            time.sleep(0.5)
        if conn is None:
            raise SystemExit("scratch TouchDesigner did not start the debug server in time")
        print(f"scratch TouchDesigner pid {proc.pid} on port {conn.port}")
        yield conn
    finally:
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGTERM)   # only the process group we started
            else:
                proc.terminate()
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        shutil.rmtree(work, ignore_errors=True)   # holds the scratch instance's connection file/token


def build_scratch(seed: Path, out: Path) -> None:
    with scratch_td(seed, live_modules=True) as conn:
        run_in_td(build_code(str(out)), conn)


VERIFY_CODE = """
import sys, td_plugin.runtime as r
comp = op('/td_python_debug')
assert comp is not None, 'no /td_python_debug in the tox'
assert type(r.__spec__.loader).__name__ == '_EmbeddedFinder', ('not embedded', r.__spec__)
assert len(str(comp.par.Token.eval())) >= 32, 'token was not generated at start'
assert comp.par.Modulepath.eval() == ''
print('embedded ok')
"""


def verify(tox: Path) -> None:
    """Open the tox alone (no Module Path anywhere): the server must start from the embedded DATs."""
    with scratch_td(tox, live_modules=False) as conn:
        status = call("td_status", connection=conn, timeout=30)
        if not status.get("ok"):
            raise SystemExit(f"verify: td_status failed: {status}")
        run_in_td(VERIFY_CODE, conn)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(TOX))
    ap.add_argument("--seed", help="tox opened in the scratch instance (default: the existing tox/td_python_debug.tox)")
    ap.add_argument("--verify-only", action="store_true", help="only open the existing tox in a scratch instance and check it runs embedded")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--attach", action="store_true", help="build in a temp COMP of the TD in the connection file instead of launching one")
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if args.verify_only:
        verify(out)
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".new.tox")
    try:
        if args.attach:
            run_in_td(build_code(str(tmp)))
        else:
            seed = Path(args.seed).resolve() if args.seed else out
            if not seed.exists():
                raise SystemExit(f"no seed tox at {seed}: pass --seed <a td-mcp tox> or use --attach")
            build_scratch(seed, tmp)
        if not tmp.exists() or tmp.stat().st_size < 1000:
            raise SystemExit("the saved tox is missing or too small")
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()
    manifest = out.with_suffix(".manifest.json")
    manifest.write_text(json.dumps({"sources": source_hashes(str(ROOT))}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes) and {manifest.name}")
    if not args.no_verify and not args.attach:
        verify(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
