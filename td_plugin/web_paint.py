"""Web paint component runtime.

TouchDesigner loads this module from the repository. The Web Render page is the
editor: a JPEG of the input TOP is pushed over a loopback WebSocket, pen strokes
stay on a canvas in the page, and the Web Render TOP is the component output.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 512


def ensure_started(comp: Any) -> None:
    server = comp.op("webserver")
    if server is None:
        return
    _bind_loopback(server)
    port = int(comp.par.Port.eval())
    _assign(server, ("port", "netport"), port)
    _assign(server, ("active",), True)
    _point_webrender(comp, port)
    comp.store("ws_clients", list(comp.fetch("ws_clients", [])))


def apply_port(comp: Any) -> None:
    server = comp.op("webserver")
    if server is None:
        return
    _assign(server, ("active",), False)
    comp.store("ws_clients", [])
    comp.store("plate_key", None)
    ensure_started(comp)


def shutdown(comp: Any) -> None:
    server = comp.op("webserver")
    if server is not None:
        _assign(server, ("active",), False)
    comp.store("ws_clients", [])


def pump(comp: Any) -> None:
    try:
        _pump(comp)
        if comp.fetch("pump_error", None) is not None:
            comp.unstore("pump_error")
    except Exception:
        message = traceback.format_exc()
        if comp.fetch("pump_error", None) != message:
            comp.store("pump_error", message)
            print(message)


def on_http(comp: Any, request: Any, response: dict) -> dict:
    if isinstance(request, dict) and comp.fetch("request_keys", None) is None:
        comp.store("request_keys", sorted(str(key) for key in request.keys()))
    path = _request_path(request)
    _log(comp, "http", path)
    if path not in ("/", "/index.html"):
        response["statusCode"] = 404
        response["statusReason"] = "Not Found"
        response["data"] = "Not found"
        return response
    response["statusCode"] = 200
    response["statusReason"] = "OK"
    response["Content-Type"] = "text/html; charset=utf-8"
    response["Cache-Control"] = "no-store"
    response["data"] = _html(comp)
    return response


def on_ws_open(comp: Any, client: Any, uri: Any = None) -> None:
    _remember(comp, client)
    _log(comp, "ws-open", f"{client} {uri or ''}".strip())
    comp.store("plate_key", None)
    pump(comp)


def on_ws_close(comp: Any, client: Any) -> None:
    comp.store("ws_clients", [item for item in comp.fetch("ws_clients", []) if item != client])
    _log(comp, "ws-close", client)


def on_ws_receive(comp: Any, client: Any, data: Any) -> None:
    _log(comp, "ws-recv", f"{client} {len(data) if data is not None else 0}")


def forward_mouse(comp: Any, down: bool) -> None:
    web = comp.op("webrender")
    if web is None:
        return
    panel = comp.panel
    u = _panel_float(panel.u)
    v = _panel_float(panel.v)
    web.interactMouse(u, 1.0 - v, left=bool(down))


def open_pane(comp: Any) -> dict:
    ui = _td().ui
    panel_type = _pane_type("PANEL")
    existing = _find_pane(ui, comp, panel_type)
    if existing is not None:
        _focus_pane(existing)
        return _pane_info(existing)
    width = _positive_int(getattr(comp.par, "w", None), DEFAULT_WIDTH)
    height = _positive_int(getattr(comp.par, "h", None), DEFAULT_HEIGHT)
    pane = ui.panes.createFloating(
        type=panel_type,
        name="Web Paint",
        maxWidth=width,
        maxHeight=height,
    )
    pane.owner = comp
    _focus_pane(pane)
    return _pane_info(pane)


def draw_test_stroke(comp: Any) -> None:
    """Drag across the middle of the page. v=0.5 is the vertical center."""
    web = comp.op("webrender")
    steps = 24
    for index in range(steps):
        u = index / (steps - 1)
        web.interactMouse(u, 0.5, left=True)
    web.interactMouse(1.0, 0.5, left=False)


def status(comp: Any) -> dict:
    web = comp.op("webrender")
    server = comp.op("webserver")
    return {
        "clients": [str(item) for item in comp.fetch("ws_clients", [])],
        "plate_key": comp.fetch("plate_key", None),
        "res_key": comp.fetch("res_key", None),
        "loaded": bool(getattr(web, "loaded", False)) if web is not None else False,
        "width": int(getattr(web, "width", 0) or 0) if web is not None else 0,
        "height": int(getattr(web, "height", 0) or 0) if web is not None else 0,
        "server_active": _eval_bool(server, "active"),
        "log": [str(item) for item in comp.fetch("event_log", [])],
        "pump_error": comp.fetch("pump_error", None),
        "request_keys": comp.fetch("request_keys", None),
        "errors": [str(item) for item in _messages(comp)],
    }


def _pump(comp: Any) -> None:
    src = comp.op("in1")
    if src is None:
        return
    upstream = _connected_source(comp, src)
    if upstream is None:
        _apply_resolution(comp, None)
        return
    try:
        src.cook(force=True)
    except Exception:
        return
    _apply_resolution(comp, src)
    if not comp.fetch("ws_clients", []):
        return
    width = int(src.width)
    height = int(src.height)
    if width <= 0 or height <= 0:
        return
    key = (upstream.path, width, height)
    time_dependent = bool(
        getattr(upstream, "timeDependent", False) or getattr(src, "timeDependent", False)
    )
    if comp.fetch("plate_key", None) == key and not time_dependent:
        return
    blob = plate_jpeg(src)
    if not blob:
        return
    _broadcast(comp, blob)
    comp.store("plate_key", key)
    _log(comp, "plate", f"{width}x{height} {len(blob)} bytes")


def plate_jpeg(top: Any) -> bytes:
    if hasattr(top, "saveByteArray"):
        try:
            data = top.saveByteArray(".jpg", quality=0.92)
        except TypeError:
            data = top.saveByteArray(".jpg")
        blob = bytes(data)
        if blob.startswith(b"\xff\xd8"):
            return blob
    import os
    import tempfile

    handle, path = tempfile.mkstemp(suffix=".jpg", prefix="web_paint_")
    os.close(handle)
    try:
        top.save(path, asynchronous=False, quality=0.92)
        return Path(path).read_bytes()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _connected_source(comp: Any, src: Any) -> Any:
    """External TOP feeding this component.

    An In TOP does not list the parent component's incoming wire in ``inputs``.
    """
    if src is not None and src.inputs:
        return src.inputs[0]
    try:
        connection = comp.inputConnectors[0].connections[0]
    except (AttributeError, IndexError, TypeError):
        return None
    owner = getattr(connection, "owner", None)
    if owner is None or owner == comp:
        return None
    return owner


def _apply_resolution(comp: Any, src: Any) -> None:
    if src is None or int(getattr(src, "width", 0) or 0) <= 0:
        width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
    else:
        width, height = int(src.width), int(src.height)
    if comp.fetch("res_key", None) == (width, height):
        return
    web = comp.op("webrender")
    if web is not None and _resize_top(web, width, height):
        comp.store("plate_key", None)
    _assign(comp, ("w",), width)
    _assign(comp, ("h",), height)
    comp.store("res_key", (width, height))


def _resize_top(top: Any, width: int, height: int) -> bool:
    changed = False
    if hasattr(top.par, "outputresolution"):
        if str(top.par.outputresolution.eval()) != "custom":
            top.par.outputresolution = "custom"
            changed = True
    if hasattr(top.par, "resolutionw") and int(top.par.resolutionw.eval()) != width:
        top.par.resolutionw = width
        changed = True
    if hasattr(top.par, "resolutionh") and int(top.par.resolutionh.eval()) != height:
        top.par.resolutionh = height
        changed = True
    return changed


def _point_webrender(comp: Any, port: int) -> None:
    web = comp.op("webrender")
    if web is None:
        return
    _set_menu(web, "source", ("urlorfile", "url", "file"))
    url = f"http://127.0.0.1:{int(port)}/"
    _assign(web, ("url", "address", "webpage"), url)
    for par in web.pars():
        if "dpi" in par.name.lower():
            try:
                par.val = 1
            except Exception:
                pass
    _assign(web, ("active",), True)


def _broadcast(comp: Any, blob: bytes) -> None:
    server = comp.op("webserver")
    if server is None:
        return
    payload = bytearray(blob)
    live = []
    for client in list(comp.fetch("ws_clients", [])):
        try:
            server.webSocketSendBinary(client, payload)
            live.append(client)
        except Exception as exc:
            _log(comp, "ws-send-failed", f"{client} {exc}")
    comp.store("ws_clients", live)


def _remember(comp: Any, client: Any) -> None:
    clients = list(comp.fetch("ws_clients", []))
    if client not in clients:
        clients.append(client)
    comp.store("ws_clients", clients)


def _html(comp: Any) -> str:
    path = Path(str(comp.par.Modulepath.eval())) / "web_paint" / "index.html"
    return path.read_text(encoding="utf-8")


def _request_path(request: Any) -> str:
    if not isinstance(request, dict):
        return "/"
    raw = request.get("uri") or request.get("path") or request.get("url") or "/"
    return str(raw).split("?", 1)[0] or "/"


def _bind_loopback(server: Any) -> None:
    for name in ("address", "ip", "host", "interface", "localaddress"):
        if not hasattr(server.par, name):
            continue
        par = getattr(server.par, name)
        try:
            names = list(getattr(par, "menuNames", []) or [])
        except Exception:
            names = []
        if names and "127.0.0.1" not in names and "localhost" not in names:
            continue
        try:
            par.val = "127.0.0.1"
        except Exception:
            pass


def _find_pane(ui: Any, comp: Any, panel_type: Any) -> Any:
    for pane in ui.panes:
        if hasattr(pane, "open") and not pane.open:
            continue
        owner = getattr(pane, "owner", None)
        if getattr(owner, "path", None) != comp.path:
            continue
        if panel_type is not None and getattr(pane, "type", None) != panel_type:
            if "PANEL" not in str(getattr(pane, "type", "")).upper():
                continue
        return pane
    return None


def _focus_pane(pane: Any) -> None:
    opener = getattr(pane, "open", None)
    if callable(opener):
        try:
            opener()
            return
        except Exception:
            pass
    try:
        pane.owner = pane.owner
    except Exception:
        pass


def _pane_type(name: str) -> Any:
    import sys

    pane_type = getattr(sys.modules.get("__main__"), "PaneType", None)
    if pane_type is None:
        from tdutils.TDDefinitions import PaneType as pane_type
    return getattr(pane_type, name)


def _pane_info(pane: Any) -> dict:
    owner = getattr(pane, "owner", None)
    return {
        "name": str(getattr(pane, "name", "")),
        "type": str(getattr(pane, "type", "")),
        "owner": getattr(owner, "path", None),
        "floating": getattr(pane, "floating", None),
        "id": getattr(pane, "id", None),
    }


def _set_menu(node: Any, name: str, choices: tuple[str, ...]) -> None:
    if not hasattr(node.par, name):
        return
    par = getattr(node.par, name)
    try:
        menu = list(par.menuNames)
    except Exception:
        menu = []
    for choice in choices:
        if not menu or choice in menu:
            par.val = choice
            return


def _assign(node: Any, names: tuple[str, ...], value: Any) -> None:
    for name in names:
        if hasattr(node.par, name):
            getattr(node.par, name).val = value
            return


def _eval_bool(node: Any, name: str) -> bool:
    if node is None or not hasattr(node.par, name):
        return False
    try:
        return bool(getattr(node.par, name).eval())
    except Exception:
        return False


def _panel_float(value: Any) -> float:
    raw = getattr(value, "val", value)
    return float(raw)


def _positive_int(par: Any, default: int) -> int:
    if par is None:
        return default
    try:
        value = int(par.eval())
    except Exception:
        return default
    return value if value > 0 else default


def _messages(node: Any) -> list[str]:
    found = []
    for name in ("errors", "scriptErrors", "warnings"):
        method = getattr(node, name, None)
        if not callable(method):
            continue
        try:
            found.extend(str(item) for item in (method() or []))
        except Exception:
            pass
    return found


def _log(comp: Any, kind: str, detail: Any) -> None:
    rows = [str(item) for item in comp.fetch("event_log", [])]
    rows.append(f"{kind}: {detail}")
    comp.store("event_log", rows[-20:])


def _td() -> Any:
    import td

    return td
