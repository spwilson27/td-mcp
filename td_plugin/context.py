"""TouchDesigner adapter used by the debug handlers."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

from td_plugin.handlers import debugpy_missing_message

FALLBACK_PYTHON = "python3"

_debugpy_port: int | None = None


class TouchDesignerContext:
    def __init__(self, comp: Any):
        self.comp = comp

    def status(self) -> dict:
        td = _td()
        version = getattr(td.app, "version", "")
        build = getattr(td.app, "build", "")
        touchdesigner = f"{version} {build}".strip()
        return {
            "ok": True,
            "python": sys.version,
            "touchdesigner": touchdesigner,
            "project": getattr(td.project, "name", ""),
            "project_folder": getattr(td.project, "folder", ""),
        }

    def resolve(self, path: str):
        return _td().op(path)

    def execution_globals(self) -> dict:
        td = _td()
        return {
            "op": td.op,
            "ops": getattr(td, "ops", None),
            "parent": td.parent,
            "me": self.comp,
            "project": td.project,
            "app": td.app,
            "ui": getattr(td, "ui", None),
            "mod": getattr(td, "mod", None),
            "ipar": getattr(td, "ipar", None),
            "td": td,
        }

    def python_executable(self) -> str:
        return find_td_python(_app())

    def start_debugpy(self, port: int) -> dict:
        try:
            debugpy = importlib.import_module("debugpy")
        except ImportError:
            return debugpy_missing_message(self.python_executable())

        global _debugpy_port
        if _debugpy_port is not None:
            if _debugpy_port != port:
                return {
                    "ok": False,
                    "error": (
                        f"debugpy is already listening on {_debugpy_port}. "
                        "Restart TouchDesigner to change ports."
                    ),
                    "port": _debugpy_port,
                }
            return {
                "ok": True,
                "already": True,
                "port": _debugpy_port,
                "connected": bool(debugpy.is_client_connected()),
            }

        try:
            debugpy.listen(("127.0.0.1", port))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        _debugpy_port = port
        return {"ok": True, "port": port, "connected": False}


def _td():
    return importlib.import_module("td")


def _app():
    try:
        return _td().app
    except Exception:
        return None


def find_td_python(app: Any = None) -> str:
    """TouchDesigner's own Python interpreter, found without assuming an install location.

    Order: $TD_MCP_PYTHON, app.pythonExecutable, sys.executable (when it is a python binary), a python binary under sys.prefix /
    app.binFolder / app.installFolder, else plain "python3".
    """
    override = os.environ.get("TD_MCP_PYTHON")
    if override:
        return override
    explicit = getattr(app, "pythonExecutable", None) if app is not None else None
    if explicit:
        return str(explicit)
    if Path(sys.executable or "").name.lower().startswith("python"):
        return sys.executable
    version = f"{sys.version_info[0]}.{sys.version_info[1]}"
    roots = [sys.prefix]
    for attr in ("binFolder", "installFolder"):
        value = getattr(app, attr, None) if app is not None else None
        if value:
            roots.append(str(value))
    for root in roots:
        base = Path(root)
        for rel in (
            f"bin/python{version}",
            "bin/python3",
            "python.exe",
            "Scripts/python.exe",
            f"Frameworks/Python.framework/Versions/{version}/bin/python{version}",
            f"../Frameworks/Python.framework/Versions/{version}/bin/python{version}",
            "bin/python.exe",
        ):
            candidate = base / rel
            if candidate.is_file():
                return str(candidate.resolve())
    return FALLBACK_PYTHON
