import json
import threading

from td_mcp.client import call, load_connection
from td_plugin.connection import connection_path as plugin_connection_path
from td_plugin.connection import write_connection
from td_plugin.runtime import Hub
from td_mcp.client import connection_path as client_connection_path


class Context:
    def status(self):
        return {"ok": True, "python": "3.11.9", "touchdesigner": "2025.0"}

    def execution_globals(self):
        return {}

    def resolve(self, path):
        return None

    def start_debugpy(self, port):
        return {"ok": True}


def test_connection_paths_match():
    assert client_connection_path() == plugin_connection_path()


def test_write_connection_is_private(tmp_path):
    dest = tmp_path / "connection.json"
    write_connection(port=8765, token="abc", path=dest)
    assert json.loads(dest.read_text()) == {"host": "127.0.0.1", "port": 8765, "token": "abc"}
    assert dest.stat().st_mode & 0o777 == 0o600


def test_load_rejects_remote_host(tmp_path):
    dest = tmp_path / "connection.json"
    dest.write_text(json.dumps({"host": "10.0.0.8", "port": 8765, "token": "abc"}))
    try:
        load_connection(dest)
    except Exception as exc:
        assert "127.0.0.1" in str(exc)
    else:
        raise AssertionError("expected rejection")


def test_call_reports_missing_touchdesigner(tmp_path):
    result = call("td_status", connection_path=tmp_path / "missing.json")
    assert result["ok"] is False
    assert "connection file" in result["error"]


def test_call_reaches_plugin(tmp_path):
    hub = Hub()
    port = hub.start("127.0.0.1", 0, "token", Context())
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            hub.pump()
            stop.wait(0.01)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    dest = write_connection(port=port, token="token", path=tmp_path / "connection.json")
    try:
        result = call("td_status", connection_path=dest)
        assert result["ok"] is True
        assert result["python"] == "3.11.9"
    finally:
        stop.set()
        hub.stop()


def test_call_when_port_is_closed(tmp_path):
    dest = write_connection(port=1, token="token", path=tmp_path / "connection.json")
    result = call("td_status", connection_path=dest, timeout=0.2)
    assert result["ok"] is False
    assert "not reachable" in result["error"]
