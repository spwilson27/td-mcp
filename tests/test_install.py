import ast
import os
from pathlib import Path

from td_plugin.install import EXECUTE_CALLBACKS, PARAMETER_CALLBACKS, repo_root


def test_callbacks_compile():
    ast.parse(EXECUTE_CALLBACKS)
    ast.parse(PARAMETER_CALLBACKS)


def test_repo_root_points_at_this_checkout():
    assert repo_root() == str(Path(__file__).resolve().parents[1])


def test_callbacks_boot_on_create_and_frame_start():
    assert "def create(" in EXECUTE_CALLBACKS
    assert "def onStart(" in EXECUTE_CALLBACKS
    assert "def onFrameStart(" in EXECUTE_CALLBACKS
    assert "runtime.ensure_started" in EXECUTE_CALLBACKS
    assert "runtime.pump" in EXECUTE_CALLBACKS
    assert 'par.name == "Start"' in PARAMETER_CALLBACKS


def test_repo_root_falls_back_to_env_home(monkeypatch, tmp_path):
    import td_plugin.install as inst

    monkeypatch.delitem(inst.__dict__, "__file__", raising=False)
    monkeypatch.setenv("TD_MCP_HOME", str(tmp_path))
    assert inst.repo_root() == str(tmp_path.resolve())
    monkeypatch.delenv("TD_MCP_HOME")
    try:
        inst.repo_root()
    except RuntimeError as exc:
        assert "<path-to-td-mcp>" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
