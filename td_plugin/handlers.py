"""Debug operations. These call a context object so tests can fake TouchDesigner."""

from __future__ import annotations

import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable

MAX_CODE_CHARS = 200_000
MAX_TEXT_CHARS = 1_000_000
MAX_OUTPUT_CHARS = 50_000
MAX_REPR_CHARS = 20_000
MAX_VISITS = 5_000
MAX_PARAMETER_LIMIT = 200
MAX_RESULT_LIMIT = 200
MAX_DEPTH = 12


def dispatch(method: str, params: dict | None, ctx: Any) -> dict:
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return {"ok": False, "error": "params must be an object"}
    handler = _METHODS.get(method)
    if handler is None:
        return {"ok": False, "error": f"Unknown method: {method}"}
    try:
        return handler(ctx, params)
    except Exception:
        return {"ok": False, "error": traceback.format_exc()}


def td_status(ctx: Any, params: dict) -> dict:
    return ctx.status()


def execute_python(ctx: Any, params: dict) -> dict:
    code = params.get("code")
    if not isinstance(code, str) or code.strip() == "":
        return {"ok": False, "error": "code must be a non-empty string"}
    if len(code) > MAX_CODE_CHARS:
        return {"ok": False, "error": f"code exceeds {MAX_CODE_CHARS} characters"}

    stdout = io.StringIO()
    stderr = io.StringIO()
    namespace = dict(ctx.execution_globals())
    try:
        compiled = compile(code, "<td-python-debug>", "eval")
        is_expr = True
    except SyntaxError:
        try:
            compiled = compile(code, "<td-python-debug>", "exec")
        except SyntaxError:
            return {
                "ok": False,
                "result": None,
                "stdout": "",
                "stderr": "",
                "traceback": traceback.format_exc(),
            }
        is_expr = False

    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            value = eval(compiled, namespace, namespace)
    except Exception:
        return {
            "ok": False,
            "result": None,
            "stdout": _truncate(stdout.getvalue(), MAX_OUTPUT_CHARS),
            "stderr": _truncate(stderr.getvalue(), MAX_OUTPUT_CHARS),
            "traceback": traceback.format_exc(),
        }

    return {
        "ok": True,
        "result": _safe_repr(value) if is_expr else None,
        "stdout": _truncate(stdout.getvalue(), MAX_OUTPUT_CHARS),
        "stderr": _truncate(stderr.getvalue(), MAX_OUTPUT_CHARS),
        "traceback": None,
    }


def read_dat(ctx: Any, params: dict) -> dict:
    node, error = _resolve_dat(ctx, params.get("path"))
    if error is not None:
        return error
    return {
        "ok": True,
        "path": node.path,
        "op_type": getattr(node, "OPType", ""),
        "text": node.text,
    }


def write_dat(ctx: Any, params: dict) -> dict:
    node, error = _resolve_dat(ctx, params.get("path"))
    if error is not None:
        return error
    text = params.get("text")
    if not isinstance(text, str):
        return {"ok": False, "error": "text must be a string"}
    if len(text) > MAX_TEXT_CHARS:
        return {"ok": False, "error": f"text exceeds {MAX_TEXT_CHARS} characters"}
    previous = node.text
    try:
        node.text = text
    except Exception as exc:
        return {"ok": False, "error": f"Could not write DAT: {exc}"}
    return {
        "ok": True,
        "path": node.path,
        "previous_length": len(previous),
        "length": len(text),
    }


def list_python_dats(ctx: Any, params: dict) -> dict:
    root, error = _resolve_existing(ctx, params.get("path") or "/")
    if error is not None:
        return error
    limit = _clamp_int(params.get("limit"), 50, 1, MAX_RESULT_LIMIT)
    max_depth = _clamp_int(params.get("max_depth"), 4, 0, MAX_DEPTH)
    found: list[dict] = []

    def visit(node: Any) -> bool:
        if not is_python_dat(node):
            return False
        found.append(_dat_summary(node))
        return True

    truncated = _walk(root, max_depth, limit, visit)
    return {"ok": True, "operators": found, "truncated": truncated}


def operator_errors(ctx: Any, params: dict) -> dict:
    root, error = _resolve_existing(ctx, params.get("path") or "/")
    if error is not None:
        return error
    limit = _clamp_int(params.get("limit"), 50, 1, MAX_RESULT_LIMIT)
    max_depth = _clamp_int(params.get("max_depth"), 4, 0, MAX_DEPTH)
    found: list[dict] = []

    def visit(node: Any) -> bool:
        errors = _messages(node, "errors")
        warnings = _messages(node, "warnings")
        script_errors = _messages(node, "scriptErrors")
        if not (errors or warnings or script_errors):
            return False
        found.append(
            {
                "path": getattr(node, "path", ""),
                "op_type": getattr(node, "OPType", ""),
                "errors": errors,
                "warnings": warnings,
                "script_errors": script_errors,
            }
        )
        return True

    truncated = _walk(root, max_depth, limit, visit)
    return {"ok": True, "operators": found, "truncated": truncated}


def describe_operator(ctx: Any, params: dict) -> dict:
    path = params.get("path")
    if not isinstance(path, str) or path == "":
        return {"ok": False, "error": "path must be a non-empty string"}
    node = ctx.resolve(path)
    if node is None:
        return {"ok": False, "error": f"Operator not found: {path}"}
    parameter_limit = _clamp_int(params.get("parameter_limit"), 40, 1, MAX_PARAMETER_LIMIT)
    parameters, truncated = _parameters(node, parameter_limit)
    return {
        "ok": True,
        "path": getattr(node, "path", path),
        "name": getattr(node, "name", ""),
        "family": getattr(node, "family", ""),
        "op_type": getattr(node, "OPType", ""),
        "errors": _messages(node, "errors"),
        "warnings": _messages(node, "warnings"),
        "script_errors": _messages(node, "scriptErrors"),
        "parameters": parameters,
        "parameters_truncated": truncated,
    }


def start_debugpy(ctx: Any, params: dict) -> dict:
    port = _clamp_int(params.get("port"), 5678, 1, 65535)
    return ctx.start_debugpy(port)


def is_python_dat(node: Any) -> bool:
    if getattr(node, "family", None) != "DAT":
        return False
    op_type = str(getattr(node, "OPType", ""))
    lowered = op_type.lower()
    if op_type == "scriptDAT" or "execute" in lowered:
        return True
    if op_type == "textDAT":
        return _language(node) == "python"
    return False


def debugpy_missing_message(executable: str) -> dict:
    return {
        "ok": False,
        "error": "debugpy is not installed in TouchDesigner's Python.",
        "install": f'"{executable}" -m pip install debugpy',
    }


def _resolve_dat(ctx: Any, path: Any) -> tuple[Any, dict | None]:
    node, error = _resolve_existing(ctx, path)
    if error is not None:
        return None, error
    if not _can_edit_text(node):
        return None, {
            "ok": False,
            "error": f"Operator is not a text DAT: {getattr(node, 'path', path)}",
        }
    return node, None


def _resolve_existing(ctx: Any, path: Any) -> tuple[Any, dict | None]:
    if not isinstance(path, str) or path == "":
        return None, {"ok": False, "error": "path must be a non-empty string"}
    node = ctx.resolve(path)
    if node is None:
        return None, {"ok": False, "error": f"Operator not found: {path}"}
    return node, None


def _can_edit_text(node: Any) -> bool:
    if getattr(node, "family", None) != "DAT":
        return False
    if getattr(node, "OPType", "") == "tableDAT":
        return False
    return isinstance(getattr(node, "text", None), str)


def _walk(root: Any, max_depth: int, limit: int, visit: Callable[[Any], bool]) -> bool:
    """Return True when the walk stops before every in-range operator is visited."""
    visited = 0
    matches = 0

    def rec(node: Any, depth: int) -> bool:
        nonlocal visited, matches
        if visited >= MAX_VISITS:
            return True
        visited += 1
        if visit(node):
            matches += 1
        if matches >= limit:
            return depth < max_depth and bool(_children(node))
        if depth >= max_depth:
            return False
        children = _children(node)
        for index, child in enumerate(children):
            child_stopped = rec(child, depth + 1)
            if matches >= limit:
                return child_stopped or index < len(children) - 1
            if child_stopped:
                return True
        return False

    return rec(root, 0)


def _children(node: Any) -> list:
    children = getattr(node, "children", None)
    if children is None:
        return []
    return list(children)


def _dat_summary(node: Any) -> dict:
    text = node.text if isinstance(getattr(node, "text", None), str) else ""
    return {
        "path": getattr(node, "path", ""),
        "op_type": getattr(node, "OPType", ""),
        "lines": text.count("\n") + (1 if text else 0),
    }


def _messages(node: Any, method_name: str) -> list[str]:
    method = getattr(node, method_name, None)
    if not callable(method):
        return []
    try:
        value = method()
    except Exception as exc:
        return [f"<failed to read {method_name}: {exc}>"]
    if not value:
        return []
    return [str(item) for item in value]


def _parameters(node: Any, limit: int) -> tuple[list[dict], bool]:
    try:
        pars = list(node.pars())
    except Exception as exc:
        return [{"name": "<error>", "value": str(exc)}], False
    described = []
    for par in pars[:limit]:
        described.append({"name": str(getattr(par, "name", "")), "value": _par_value(par)})
    return described, len(pars) > limit


def _par_value(par: Any) -> str:
    try:
        value = par.eval()
    except Exception as exc:
        return f"<error: {exc}>"
    if isinstance(value, tuple) and len(value) == 1:
        value = value[0]
    try:
        text = str(value)
    except Exception as exc:
        return f"<error: {exc}>"
    return _truncate(text, 500)


def _language(node: Any) -> str:
    par = getattr(node, "par", None)
    if par is None or not hasattr(par, "language"):
        return ""
    try:
        value = par.language.eval()
    except Exception:
        return ""
    if isinstance(value, tuple) and len(value) == 1:
        value = value[0]
    return str(value).lower()


def _safe_repr(value: Any) -> str:
    try:
        text = repr(value)
    except Exception as exc:
        text = f"<unrepresentable: {exc}>"
    return _truncate(text, MAX_REPR_CHARS)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    if value is None or value == "":
        parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
    return max(low, min(high, parsed))


_METHODS = {
    "td_status": td_status,
    "execute_python": execute_python,
    "read_dat": read_dat,
    "write_dat": write_dat,
    "list_python_dats": list_python_dats,
    "operator_errors": operator_errors,
    "describe_operator": describe_operator,
    "start_debugpy": start_debugpy,
}
