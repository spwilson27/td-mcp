import json

import pytest

import td_plugin.runtime as runtime
from td_mcp.client import ConnectionConfigError, call, connection_path as client_path, load_connection
from td_plugin.connection import connection_path as plugin_path, write_connection


class Par:
    def __init__(self, v):
        self.v = v

    def eval(self):
        return self.v


class Comp:
    class par:
        Port = Par(8765)


def test_connection_override_shared_by_plugin_and_client(monkeypatch, tmp_path):
    dest = tmp_path / "w0" / "connection.json"
    monkeypatch.setenv("TD_MCP_CONNECTION", str(dest))
    assert client_path() == plugin_path() == dest
    write_connection(port=18770, token="t")
    assert json.loads(dest.read_text())["port"] == 18770
    assert load_connection().port == 18770


def test_default_connection_path_without_override(monkeypatch):
    monkeypatch.delenv("TD_MCP_CONNECTION", raising=False)
    assert client_path().name == "connection.json" and client_path().parent.name == ".td-mcp"


def test_missing_file_message_names_the_actual_path(monkeypatch, tmp_path):
    dest = tmp_path / "nope.json"
    monkeypatch.setenv("TD_MCP_CONNECTION", str(dest))
    with pytest.raises(ConnectionConfigError) as e:
        load_connection()
    assert str(dest) in str(e.value) and "~/.td-mcp" not in str(e.value)
    assert str(dest) in call("td_status")["error"]


def test_port_env_overrides_parameter(monkeypatch):
    monkeypatch.setenv("TD_MCP_PORT", "18771")
    assert runtime._port_for(Comp) == 18771


@pytest.mark.parametrize("bad", ["abc", "70000", "-1", "1.5"])
def test_invalid_port_env_logs_and_falls_back(monkeypatch, capsys, bad):
    monkeypatch.setenv("TD_MCP_PORT", bad)
    assert runtime._port_for(Comp) == 8765
    assert "ignoring invalid TD_MCP_PORT" in capsys.readouterr().out


def test_no_port_env_uses_parameter(monkeypatch):
    monkeypatch.delenv("TD_MCP_PORT", raising=False)
    monkeypatch.setenv("TD_MCP_PORT", "")
    assert runtime._port_for(Comp) == 8765
