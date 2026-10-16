"""Build the debug component inside an open TouchDesigner project.

Preferred: drag tox/td_python_debug.tox into the project (self-contained, no checkout needed).

Dev install (live code from a checkout), from the Textport:

    p = "<path-to-td-mcp>/td_plugin/install.py"; exec(compile(open(p).read(), p, "exec"), {**globals(), "__file__": p})
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

DEFAULT_PORT = 8765

TEXTPORT_HINT = (
    'p = "<path-to-td-mcp>/td_plugin/install.py"; '
    'exec(compile(open(p).read(), p, "exec"), {**globals(), "__file__": p})'
)

MODULES = ("td_plugin", "td_plugin.connection", "td_plugin.context", "td_plugin.handlers", "td_plugin.runtime")

# Text DAT `bootstrap` inside the component. Resolves where `td_plugin` comes from, in this order:
#   1. the `Modulepath` parameter, when not empty (dev override: live code from a checkout);
#   2. the TD_MCP_MODULEPATH environment variable;
#   3. the `mod_*` DATs embedded in the component (no checkout needed).
BOOTSTRAP = '''\
import importlib.abc
import importlib.util
import os
import sys

_MARK = "_td_mcp_embedded_finder"


def dat_name(modname):
    tail = modname.split(".", 1)[1] if "." in modname else "init"
    return "mod_" + tail


class _EmbeddedFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    _td_mcp_embedded_finder = True

    def __init__(self, comp_path):
        self.comp_path = comp_path

    def _dat(self, name):
        comp = op(self.comp_path)
        return comp.op(dat_name(name)) if comp is not None else None

    def find_spec(self, name, path=None, target=None):
        if name != "td_plugin" and not name.startswith("td_plugin."):
            return None
        if self._dat(name) is None:
            return None
        return importlib.util.spec_from_loader(name, self, is_package=(name == "td_plugin"))

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        dat = self._dat(module.__name__)
        exec(compile(dat.text, "<td_mcp embedded %s>" % dat.name, "exec"), module.__dict__)


def _remove_finders():
    sys.meta_path[:] = [f for f in sys.meta_path if not getattr(f, _MARK, False)]


def module_path(comp):
    return str(comp.par.Modulepath.eval() or "").strip() or os.environ.get("TD_MCP_MODULEPATH", "").strip()


def prepare(comp):
    """Make `import td_plugin.*` resolve per the order above. Cheap; safe to call every frame."""
    path = module_path(comp)
    if path:
        _remove_finders()
        if path not in sys.path:
            sys.path.insert(0, path)
        return "path"
    current = [f for f in sys.meta_path if getattr(f, _MARK, False)]
    if current and current[0].comp_path == comp.path and sys.meta_path[0] is current[0]:
        return "embedded"
    _remove_finders()
    sys.meta_path.insert(0, _EmbeddedFinder(comp.path))
    return "embedded"
'''

EXECUTE_CALLBACKS = '''\
def _report_once(exc):
    if getattr(_report_once, "reported", False):
        return
    _report_once.reported = True
    print("td-python-debug failed to import:", exc)


def _prepare():
    comp = parent()
    comp.op("bootstrap").module.prepare(comp)
    return comp


def _boot():
    try:
        comp = _prepare()
        import td_plugin.runtime as runtime
    except Exception as exc:
        _report_once(exc)
        return
    if comp.par.Autostart.eval():
        runtime.ensure_started(comp)


def onStart():
    _boot()
    return


def create():
    _boot()
    return


def onCreate():
    _boot()
    return


def onFrameStart(frame):
    try:
        _prepare()
        import td_plugin.runtime as runtime
    except Exception as exc:
        _report_once(exc)
        return
    runtime.pump()
    return


def onExit():
    try:
        _prepare()
        import td_plugin.runtime as runtime
    except Exception as exc:
        _report_once(exc)
        return
    runtime.stop()
    return
'''

PARAMETER_CALLBACKS = '''\
def _report_once(exc):
    if getattr(_report_once, "reported", False):
        return
    _report_once.reported = True
    print("td-python-debug failed to import:", exc)


def onPulse(par):
    try:
        comp = parent()
        comp.op("bootstrap").module.prepare(comp)
        import td_plugin.runtime as runtime
    except Exception as exc:
        _report_once(exc)
        return
    if par.name == "Start":
        runtime.ensure_started(comp, force=True)
    elif par.name == "Stop":
        runtime.stop()
    return
'''


def repo_root() -> str:
    """The td-mcp checkout this file was loaded from (or $TD_MCP_HOME)."""
    file = globals().get("__file__")
    if file:
        return str(Path(file).resolve().parent.parent)
    home = os.environ.get("TD_MCP_HOME")
    if home:
        return str(Path(home).expanduser().resolve())
    raise RuntimeError(
        "Cannot locate the td-mcp checkout. Run the installer with its path, or set TD_MCP_HOME:\n" + TEXTPORT_HINT
    )


def module_dat_name(modname: str) -> str:
    tail = modname.split(".", 1)[1] if "." in modname else "init"
    return "mod_" + tail


def module_file(root: str, modname: str) -> Path:
    base = Path(root) / modname.replace(".", "/")
    return base / "__init__.py" if modname == "td_plugin" else base.with_suffix(".py")


def component_sources(root: str) -> dict:
    """DAT name -> text for every DAT embedded in the component, in a stable order."""
    sources = {"bootstrap": BOOTSTRAP, "callbacks": EXECUTE_CALLBACKS, "par_callbacks": PARAMETER_CALLBACKS}
    for modname in MODULES:
        text = module_file(root, modname).read_text(encoding="utf-8")
        sources[module_dat_name(modname)] = text.replace("\r\n", "\n")
    return sources


def source_hashes(root: str) -> dict:
    return {
        name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in component_sources(root).items()
    }


def build_component(parent_comp, root: str, module_path: str = "", name: str = "td_python_debug", start: bool = True):
    """Create the debug component under `parent_comp` (a TD COMP).

    `module_path` goes in the Modulepath parameter ("" = use the embedded modules). With `start=False` nothing is started and the
    component keeps Token blank: used to build the shipped tox (scripts/build_tox.py).
    """
    import td

    existing = parent_comp.op(name)
    if existing is not None:
        existing.destroy()

    base = parent_comp.create(td.baseCOMP, name)
    base.nodeX = 0
    base.nodeY = -400
    try:
        base.comment = "Python debug MCP"
    except Exception:
        pass

    page = base.appendCustomPage("Debug")
    port = _first_par(page.appendInt("Port", label="Port"))
    _assign(port, DEFAULT_PORT)

    autostart = _first_par(page.appendToggle("Autostart", label="Auto Start"))
    _assign(autostart, True)
    if not start:
        autostart.val = False   # restored at the end: nothing may boot while the component is being built

    mp = _first_par(page.appendStr("Modulepath", label="Module Path"))
    _assign(mp, module_path)

    # Blank: the runtime generates a random token at first start and stores it here.
    token_par = _first_par(page.appendStr("Token", label="Token"))
    _assign(token_par, "")

    _first_par(page.appendPulse("Start", label="Start"))
    _first_par(page.appendPulse("Stop", label="Stop"))

    sources = component_sources(root)
    for i, (dat_name, text) in enumerate(sources.items()):
        if dat_name in ("callbacks", "par_callbacks"):
            continue
        dat = base.create(td.textDAT, dat_name)
        dat.text = text
        dat.nodeX = 400 + (i % 4) * 200
        dat.nodeY = -(i // 4) * 150

    callbacks = base.create(td.executeDAT, "callbacks")
    callbacks.text = sources["callbacks"]
    callbacks.nodeX = 0
    callbacks.nodeY = 0
    _enable(callbacks, "start", True)
    _enable(callbacks, "create", True)
    _enable(callbacks, "framestart", True)
    _enable(callbacks, "exit", True)
    _set_language(callbacks)

    pulses = base.create(td.parameterexecuteDAT, "par_callbacks")
    pulses.text = sources["par_callbacks"]
    pulses.nodeX = 200
    pulses.nodeY = 0
    _enable(pulses, "active", True)
    _enable(pulses, "onpulse", True)
    _enable(pulses, "valuechange", False)
    _enable(pulses, "custom", True)
    _enable(pulses, "builtin", False)
    if hasattr(pulses.par, "pars"):
        pulses.par.pars.val = "*"
    if hasattr(pulses.par, "op"):
        pulses.par.op.expr = "parent()"
    _set_language(pulses)

    # Last: with active on, the callbacks boot the server (Auto Start) and pump it every frame.
    _enable(callbacks, "active", True)
    if not start:
        autostart.val = True
    return base


def install() -> None:
    """Dev install into the open project: Modulepath points at this checkout (live code); the modules are embedded as a fallback."""
    import td

    root = repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    parent_comp = td.op("/project1")
    if parent_comp is None:
        parent_comp = td.op("/")
    base = build_component(parent_comp, root, module_path=root, start=True)

    from td_plugin.runtime import ensure_started

    ensure_started(base, force=True)
    print(f"Installed {base.path}.")
    print("Save the project (Cmd+S) so this component loads the next time TouchDesigner starts.")


def _first_par(created):
    if isinstance(created, (list, tuple)):
        return created[0]
    try:
        return created[0]
    except Exception:
        return created


def _assign(par, value) -> None:
    par.val = value
    try:
        par.default = value
    except Exception:
        pass


def _enable(dat, name: str, value: bool) -> None:
    if hasattr(dat.par, name):
        getattr(dat.par, name).val = value


def _set_language(dat) -> None:
    if hasattr(dat.par, "language"):
        dat.par.language.val = "python"


def _td_name(name: str):
    if name in globals():
        return globals()[name]
    builtins = globals().get("__builtins__")
    mapping = builtins if isinstance(builtins, dict) else getattr(builtins, "__dict__", {})
    return mapping.get(name)


def _running_inside_touchdesigner() -> bool:
    return _td_name("op") is not None and _td_name("baseCOMP") is not None


def _launch() -> None:
    if not _running_inside_touchdesigner():
        if __name__ == "__main__":
            print(
                "Run this from the TouchDesigner Textport:\n" + TEXTPORT_HINT
            )
        return
    print("td-python-debug installer starting")
    try:
        install()
    except Exception:
        import traceback

        traceback.print_exc()
        print("td-python-debug installer failed. The traceback above is the reason.")


_launch()
