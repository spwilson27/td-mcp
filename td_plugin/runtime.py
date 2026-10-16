"""Localhost server. TouchDesigner drains the queue on the main thread."""

from __future__ import annotations

import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from typing import Any

from td_plugin.connection import DEFAULT_HOST, write_connection
from td_plugin.context import TouchDesignerContext
from td_plugin.handlers import dispatch

MAX_BODY_BYTES = 2_000_000
MAX_TIMEOUT_SECONDS = 120.0


class Job:
    def __init__(self, method: str, params: dict):
        self.method = method
        self.params = params
        self.event = threading.Event()
        self.result: dict | None = None
        self.error: str | None = None


class Hub:
    def __init__(self):
        self.queue: Queue[Job] = Queue()
        self.server: ThreadingHTTPServer | None = None
        self.token = ""
        self.context: Any = None
        self.running = False
        self._lock = threading.Lock()

    def start(self, host: str, port: int, token: str, context: Any) -> int:
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Debug server must bind to loopback")
        with self._lock:
            self._stop_locked()
            self.token = token
            self.context = context
            self.server = ThreadingHTTPServer((host, int(port)), _make_handler(self))
            self.server.daemon_threads = True
            thread = threading.Thread(
                target=self.server.serve_forever,
                name="td-python-debug",
                daemon=True,
            )
            thread.start()
            self.running = True
            bound_port = int(self.server.server_address[1])
            _wait_until_listening(host, bound_port)
            return bound_port

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def pump(self) -> None:
        while True:
            try:
                job = self.queue.get_nowait()
            except Empty:
                return
            try:
                job.result = dispatch(job.method, job.params, self.context)
            except Exception:
                job.error = traceback.format_exc()
            finally:
                job.event.set()

    def _stop_locked(self) -> None:
        server = self.server
        self.server = None
        self.running = False
        if server is not None:
            server.shutdown()
            server.server_close()


_hub: Hub | None = None


def get_hub() -> Hub:
    global _hub
    if _hub is None:
        _hub = Hub()
    return _hub


def _port_for(comp: Any) -> int:
    """The `Port` parameter, unless TD_MCP_PORT (a valid port number) overrides it; an invalid value is logged and ignored."""
    raw = os.environ.get("TD_MCP_PORT")
    if raw:
        try:
            value = int(raw)
            if 0 <= value <= 65535:
                return value
        except ValueError:
            pass
        print(f"td-python-debug: ignoring invalid TD_MCP_PORT={raw!r}; using the Port parameter")
    return int(comp.par.Port.eval())


def ensure_started(comp: Any, force: bool = False) -> None:
    hub = get_hub()
    if hub.running and not force:
        return
    module_path = str(comp.par.Modulepath.eval())
    _insert_module_path(module_path)
    port = _port_for(comp)
    token = str(comp.par.Token.eval() or "")
    if token == "":
        import secrets

        token = secrets.token_urlsafe(32)
        comp.par.Token.val = token
    try:
        bound = hub.start(DEFAULT_HOST, port, token, TouchDesignerContext(comp))
    except OSError as exc:
        print(f"td-python-debug failed to listen on {DEFAULT_HOST}:{port}: {exc}")
        return
    write_connection(port=bound, token=token, host=DEFAULT_HOST)
    print(f"td-python-debug listening on {DEFAULT_HOST}:{bound}")


def pump() -> None:
    hub = get_hub()
    if hub.running:
        hub.pump()


def stop() -> None:
    hub = get_hub()
    was_running = hub.running
    hub.stop()
    if was_running:
        print("td-python-debug stopped")


def _wait_until_listening(host: str, port: int) -> None:
    import socket
    import time

    last_error: Exception | None = None
    for _ in range(50):
        try:
            with socket.create_connection((host, port), timeout=0.05):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.01)
    raise OSError(f"debug server did not listen on {host}:{port}: {last_error}")


def _insert_module_path(module_path: str) -> None:
    import sys

    if module_path and module_path not in sys.path:
        sys.path.insert(0, module_path)


def _make_handler(hub: Hub):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] != "/health":
                self._send(404, {"error": {"message": "not found"}})
                return
            self._send(200, {"ok": True, "service": "td-python-debug"})

        def do_POST(self) -> None:
            if self.path.split("?", 1)[0] != "/rpc":
                self._send(404, {"error": {"message": "not found"}})
                return
            if not _authorized(self.headers.get("Authorization", ""), hub.token):
                self._send(401, {"error": {"message": "unauthorized"}})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400, {"error": {"message": "invalid content length"}})
                return
            if length < 0 or length > MAX_BODY_BYTES:
                self._send(400, {"error": {"message": "request body is too large"}})
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"error": {"message": "request body must be JSON"}})
                return
            if not isinstance(body, dict) or not isinstance(body.get("method"), str):
                self._send(400, {"error": {"message": "method must be a string"}})
                return
            params = body.get("params") or {}
            if not isinstance(params, dict):
                self._send(400, {"error": {"message": "params must be an object"}})
                return
            timeout = _timeout(body.get("timeout"))
            job = Job(body["method"], params)
            hub.queue.put(job)
            if not job.event.wait(timeout):
                self._send(
                    504,
                    {
                        "error": {
                            "message": (
                                "Timed out waiting for the TouchDesigner main thread. "
                                "The project may be paused on a dialog, or cooking may be stopped."
                            )
                        }
                    },
                )
                return
            if job.error:
                self._send(500, {"error": {"message": job.error}})
                return
            self._send(200, {"result": job.result})

        def _send(self, status: int, payload: dict) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def _authorized(header: str, token: str) -> bool:
    import hmac

    expected = f"Bearer {token}"
    if len(header) != len(expected):
        return False
    return hmac.compare_digest(header, expected)


def _timeout(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 30.0
    if parsed <= 0:
        parsed = 30.0
    return min(parsed, MAX_TIMEOUT_SECONDS)
