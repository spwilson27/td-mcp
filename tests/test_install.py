import ast
from pathlib import Path

from td_plugin.install import DEFAULT_REPO, EXECUTE_CALLBACKS, PARAMETER_CALLBACKS, repo_root


def test_callbacks_compile():
    ast.parse(EXECUTE_CALLBACKS)
    ast.parse(PARAMETER_CALLBACKS)


def test_repo_root_points_at_this_checkout():
    assert repo_root() == str(Path(__file__).resolve().parents[1])
    assert DEFAULT_REPO == "/Users/mrwilson/software/td-mcp"


def test_callbacks_boot_on_create_and_frame_start():
    assert "def create(" in EXECUTE_CALLBACKS
    assert "def onStart(" in EXECUTE_CALLBACKS
    assert "def onFrameStart(" in EXECUTE_CALLBACKS
    assert "runtime.ensure_started" in EXECUTE_CALLBACKS
    assert "runtime.pump" in EXECUTE_CALLBACKS
    assert 'par.name == "Start"' in PARAMETER_CALLBACKS
