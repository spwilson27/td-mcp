"""Build the debug component inside an open TouchDesigner project.

Run from the Textport:

    exec(open("/Users/mrwilson/software/td-mcp/td_plugin/install.py").read(), globals())
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

DEFAULT_REPO = "/Users/mrwilson/software/td-mcp"

EXECUTE_CALLBACKS = '''\
def _report_once(exc):
    if getattr(_report_once, "reported", False):
        return
    _report_once.reported = True
    print("td-python-debug failed to import:", exc)


def _prepare():
    comp = parent()
    module_path = comp.par.Modulepath.eval()
    import sys
    if module_path and module_path not in sys.path:
        sys.path.insert(0, module_path)
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
        module_path = comp.par.Modulepath.eval()
        import sys
        if module_path and module_path not in sys.path:
            sys.path.insert(0, module_path)
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
    file = globals().get("__file__")
    if file:
        return str(Path(file).resolve().parent.parent)
    return DEFAULT_REPO


def install() -> None:
    root = repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    parent_comp = op("/project1")
    if parent_comp is None:
        parent_comp = op("/")
    existing = parent_comp.op("td_python_debug")
    if existing is not None:
        existing.destroy()

    base = parent_comp.create(baseCOMP, "td_python_debug")
    base.nodeX = 0
    base.nodeY = -400
    try:
        base.comment = "Python debug MCP"
    except Exception:
        pass

    page = base.appendCustomPage("Debug")
    port = _first_par(page.appendInt("Port", label="Port"))
    _assign(port, 8765)

    autostart = _first_par(page.appendToggle("Autostart", label="Auto Start"))
    _assign(autostart, True)

    module_path = _first_par(page.appendStr("Modulepath", label="Module Path"))
    _assign(module_path, root)

    token = secrets.token_urlsafe(32)
    token_par = _first_par(page.appendStr("Token", label="Token"))
    _assign(token_par, token)

    _first_par(page.appendPulse("Start", label="Start"))
    _first_par(page.appendPulse("Stop", label="Stop"))

    callbacks = base.create(executeDAT, "callbacks")
    callbacks.text = EXECUTE_CALLBACKS
    callbacks.nodeX = 0
    callbacks.nodeY = 0
    _enable(callbacks, "active", True)
    _enable(callbacks, "start", True)
    _enable(callbacks, "create", True)
    _enable(callbacks, "framestart", True)
    _enable(callbacks, "exit", True)
    _set_language(callbacks)

    pulses = base.create(parameterexecuteDAT, "par_callbacks")
    pulses.text = PARAMETER_CALLBACKS
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
                "Run this from the TouchDesigner Textport:\n"
                "exec(open('/Users/mrwilson/software/td-mcp/td_plugin/install.py').read(), globals())"
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
