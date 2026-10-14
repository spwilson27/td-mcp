"""TouchDesigner adapter used by the debug handlers."""

from __future__ import annotations

import importlib
import sys
from typing import Any

from td_plugin.handlers import debugpy_missing_message

TD_PYTHON = (
    "/Applications/TouchDesigner.app/Contents/Frameworks/"
    "Python.framework/Versions/3.11/bin/python3.11"
)

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
        try:
            executable = getattr(_td().app, "pythonExecutable", None)
        except Exception:
            executable = None
        if executable:
            return str(executable)
        return TD_PYTHON

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
