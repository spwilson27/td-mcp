"""Build the web paint component inside an open TouchDesigner project.

Run from the Textport:

    exec(open("/Users/mrwilson/software/td-mcp/td_plugin/web_paint_install.py").read(), globals())
"""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_REPO = "/Users/mrwilson/software/td-mcp"
DEFAULT_PORT = 9876

PRELUDE = '''\
def _web_paint():
    comp = parent()
    module_path = ""
    if hasattr(comp.par, "Modulepath"):
        module_path = comp.par.Modulepath.eval()
    import sys
    if module_path and module_path not in sys.path:
        sys.path.insert(0, module_path)
    import td_plugin.web_paint as web_paint
    return comp, web_paint
'''

FRAME_CALLBACKS = PRELUDE + '''\

def onStart():
    comp, web_paint = _web_paint()
    web_paint.ensure_started(comp)
    return


def onCreate():
    onStart()
    return


def onFrameStart(frame):
    comp, web_paint = _web_paint()
    web_paint.pump(comp)
    return


def onExit():
    comp, web_paint = _web_paint()
    web_paint.shutdown(comp)
    return
'''

PARAMETER_CALLBACKS = PRELUDE + '''\

def onPulse(par):
    if par.name != "Open":
        return
    comp, web_paint = _web_paint()
    info = web_paint.open_pane(comp)
    print("web_paint pane", info)
    return


def onValueChange(par, prev):
    if par.name != "Port":
        return
    comp, web_paint = _web_paint()
    web_paint.apply_port(comp)
    return
'''

PANEL_CALLBACKS = PRELUDE + '''\

def onOffToOn(panelValue):
    comp, web_paint = _web_paint()
    web_paint.forward_mouse(comp, True)
    return


def whileOn(panelValue):
    comp, web_paint = _web_paint()
    web_paint.forward_mouse(comp, True)
    return


def onOnToOff(panelValue):
    comp, web_paint = _web_paint()
    web_paint.forward_mouse(comp, False)
    return
'''

HTTP_CALLBACKS = PRELUDE + '''\

def onHTTPRequest(dat, request, response):
    comp, web_paint = _web_paint()
    return web_paint.on_http(comp, request, response)


def onWebSocketOpen(dat, client, uri):
    comp, web_paint = _web_paint()
    web_paint.on_ws_open(comp, client, uri)
    return


def onWebSocketClose(dat, client):
    comp, web_paint = _web_paint()
    web_paint.on_ws_close(comp, client)
    return


def onWebSocketReceiveText(dat, client, data):
    comp, web_paint = _web_paint()
    web_paint.on_ws_receive(comp, client, data)
    return


def onWebSocketReceiveBinary(dat, client, data):
    comp, web_paint = _web_paint()
    web_paint.on_ws_receive(comp, client, data)
    return
'''


def repo_root() -> str:
    file = globals().get("__file__")
    if file:
        return str(Path(file).resolve().parent.parent)
    return DEFAULT_REPO


def install() -> None:
    import importlib

    import td

    root = repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    parent_comp = td.op("/project1")
    if parent_comp is None:
        parent_comp = td.op("/")

    existing = parent_comp.op("web_paint")
    if existing is not None:
        for child in existing.children:
            if hasattr(child.par, "active"):
                try:
                    child.par.active = False
                except Exception:
                    pass
        existing.destroy()

    base = parent_comp.create(_type(td, "containerCOMP"), "web_paint")
    base.nodeX = 400
    base.nodeY = -400
    try:
        base.comment = "Web paint"
    except Exception:
        pass

    page = base.appendCustomPage("Paint")
    port = _first_par(page.appendInt("Port", label="Port"))
    _assign(port, DEFAULT_PORT)
    module_path = _first_par(page.appendStr("Modulepath", label="Module Path"))
    _assign(module_path, root)
    _first_par(page.appendPulse("Open", label="Open Web UI"))

    enter = base.create(_type(td, "inTOP"), "in1")
    enter.nodeX = 0
    enter.nodeY = 200

    web = base.create(_type(td, "webrenderTOP"), "webrender")
    web.nodeX = 0
    web.nodeY = 0
    web.viewer = True

    out = base.create(_type(td, "outTOP"), "out1")
    out.nodeX = 0
    out.nodeY = -150
    out.inputConnectors[0].connect(web.outputConnectors[0])

    http = _script(base, _type(td, "textDAT"), "http_callbacks", HTTP_CALLBACKS, 250, 0)
    server = base.create(_type(td, "webserverDAT"), "webserver")
    server.nodeX = 250
    server.nodeY = 200
    _prepare_server(server, http)
    generated = base.op("webserver_callbacks")
    if generated is not None and generated != http:
        generated.destroy()

    _script(base, _type(td, "executeDAT"), "frame_callbacks", FRAME_CALLBACKS, 500, 200)
    _script(base, _type(td, "parameterexecuteDAT"), "par_callbacks", PARAMETER_CALLBACKS, 500, 0)
    _script(base, _type(td, "panelexecuteDAT"), "panel_callbacks", PANEL_CALLBACKS, 750, 0)

    _configure_frame(base.op("frame_callbacks"))
    _configure_parameters(base.op("par_callbacks"))
    _configure_panel(base.op("panel_callbacks"))
    _configure_background(base)
    _assign_size(base, 512, 512)

    module = importlib.import_module("td_plugin.web_paint")
    importlib.reload(module)
    module.ensure_started(base)
    print(f"Installed {base.path}.")
    print(f"Open Web UI loads http://127.0.0.1:{DEFAULT_PORT}/")


def _prepare_server(server, callbacks) -> None:
    if hasattr(server.par, "active"):
        server.par.active = False
    callback_par = _find_par(server, "callbacks", "callbackdat", "callback")
    if callback_par is None:
        raise RuntimeError(f"Web Server DAT has no callbacks parameter: {_names(server)}")
    callback_par.val = callbacks.path
    port_par = _find_par(server, "port", "netport")
    if port_par is None:
        raise RuntimeError(f"Web Server DAT has no port parameter: {_names(server)}")
    port_par.val = DEFAULT_PORT


def _configure_frame(dat) -> None:
    _enable(dat, "active", True)
    _enable(dat, "start", True)
    _enable(dat, "create", True)
    _enable(dat, "framestart", True)
    _enable(dat, "exit", True)


def _configure_parameters(dat) -> None:
    _enable(dat, "active", True)
    _enable(dat, "onpulse", True)
    _enable(dat, "valuechange", True)
    _enable(dat, "custom", True)
    _enable(dat, "builtin", False)
    if hasattr(dat.par, "pars"):
        dat.par.pars.val = "*"
    target = _find_par(dat, "op", "ops", "parameters")
    if target is not None:
        try:
            target.expr = "parent()"
        except Exception:
            target.val = dat.parent().path


def _configure_panel(dat) -> None:
    _enable(dat, "active", True)
    _enable(dat, "offtoon", True)
    _enable(dat, "whileon", True)
    _enable(dat, "ontooff", True)
    _enable(dat, "valuechange", False)
    target = _find_par(dat, "panels", "panel", "op", "ops")
    if target is None:
        raise RuntimeError(f"Panel Execute DAT has no panel parameter: {_names(dat)}")
    try:
        target.expr = "parent()"
    except Exception:
        target.val = dat.parent().path
    value = _find_par(dat, "panelvalue", "panelvalues")
    if value is not None:
        _set_choice(value, "lselect")


def _configure_background(comp) -> None:
    top = _find_par(comp, "top", "bgop", "backgroundtop")
    if top is None:
        return
    web = comp.op("webrender")
    try:
        top.val = web
    except Exception:
        top.expr = "me.op('webrender')"


def _assign_size(comp, width: int, height: int) -> None:
    if hasattr(comp.par, "w"):
        comp.par.w = width
    if hasattr(comp.par, "h"):
        comp.par.h = height


def _script(parent, op_type, name: str, text: str, node_x: int, node_y: int):
    dat = parent.create(op_type, name)
    dat.text = text
    dat.nodeX = node_x
    dat.nodeY = node_y
    _set_language(dat)
    return dat


def _type(td, name: str):
    if hasattr(td, name):
        return getattr(td, name)
    found = [item for item in dir(td) if item.lower() == name.lower()]
    if found:
        return getattr(td, found[0])
    raise RuntimeError(f"This TouchDesigner build has no {name}.")


def _find_par(node, *names):
    for name in names:
        if hasattr(node.par, name):
            return getattr(node.par, name)
    return None


def _set_choice(par, choice: str) -> None:
    try:
        menu = list(par.menuNames)
    except Exception:
        menu = []
    if not menu or choice in menu:
        par.val = choice


def _names(node) -> str:
    try:
        return ", ".join(par.name for par in node.pars())
    except Exception:
        return ""


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


def _launch() -> None:
    try:
        import td

        if td.op is None:
            raise RuntimeError("TouchDesigner op is unavailable")
    except Exception:
        print(
            "Run this from the TouchDesigner Textport:\n"
            "exec(open('/Users/mrwilson/software/td-mcp/td_plugin/web_paint_install.py').read(), globals())"
        )
        return
    print("web_paint installer starting")
    try:
        install()
    except Exception:
        import traceback

        traceback.print_exc()
        print("web_paint installer failed. The traceback above is the reason.")


_launch()
