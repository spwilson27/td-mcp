"""HTTP bridge tests. A background thread stands in for TouchDesigner's main thread."""

import json
import threading
import urllib.error
import urllib.request

from td_plugin.handlers import dispatch
from td_plugin.runtime import Hub


class Context:
    def status(self):
        return {"ok": True, "python": "3.11"}

    def execution_globals(self):
        return {}

    def resolve(self, path):
        return None

    def start_debugpy(self, port):
        return {"ok": True, "port": port}


def _pump_until(hub, stop):
    while not stop.is_set():
        hub.pump()
        stop.wait(0.01)


def _start(token="secret"):
    hub = Hub()
    port = hub.start("127.0.0.1", 0, token, Context())
    stop = threading.Event()
    thread = threading.Thread(target=_pump_until, args=(hub, stop), daemon=True)
    thread.start()
    return hub, port, stop


def _post(port, payload, token="secret"):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/rpc",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode())


def test_rpc_round_trip():
    hub, port, stop = _start()
    try:
        body = _post(port, {"method": "execute_python", "params": {"code": "1 + 2"}})
        assert body["result"]["ok"] is True
        assert body["result"]["result"] == "3"
    finally:
        stop.set()
        hub.stop()


def test_rejects_missing_token():
    hub, port, stop = _start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/rpc",
            data=b'{"method": "td_status", "params": {}}',
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("expected 401")
    finally:
        stop.set()
        hub.stop()


def test_times_out_without_main_thread():
    hub = Hub()
    port = hub.start("127.0.0.1", 0, "secret", Context())
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/rpc",
            data=b'{"method": "td_status", "params": {}, "timeout": 0.2}',
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 504
        else:
            raise AssertionError("expected 504")
    finally:
        hub.stop()


def test_refuses_non_loopback_bind():
    try:
        Hub().start("0.0.0.0", 0, "secret", Context())
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_dispatch_used_by_hub():
    assert dispatch("td_status", {}, Context())["python"] == "3.11"
