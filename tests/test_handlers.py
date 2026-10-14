"""Handler tests against a fake operator tree."""

from types import SimpleNamespace

from td_plugin.context import TD_PYTHON, TouchDesignerContext
from td_plugin.handlers import dispatch


class FakePar:
    def __init__(self, name, value):
        self.name = name
        self._value = value

    def eval(self):
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class FakeOp:
    def __init__(
        self,
        path,
        family="COMP",
        op_type="baseCOMP",
        text=None,
        children=None,
        errors=None,
        warnings=None,
        script_errors=None,
        pars=None,
        language=None,
    ):
        self.path = path
        self.name = path.rstrip("/").rsplit("/", 1)[-1] or "/"
        self.family = family
        self.OPType = op_type
        self.text = text
        self.children = children or []
        self._errors = errors or []
        self._warnings = warnings or []
        self._script_errors = script_errors or []
        self._pars = pars or []
        self.par = SimpleNamespace()
        if language is not None:
            self.par.language = FakePar("language", language)

    def errors(self):
        return list(self._errors)

    def warnings(self):
        return list(self._warnings)

    def scriptErrors(self):
        return list(self._script_errors)

    def pars(self):
        return list(self._pars)


class FakeContext:
    def __init__(self, operators):
        self.operators = operators
        self.started = []

    def status(self):
        return {"ok": True, "python": "3.11.0", "touchdesigner": "test"}

    def resolve(self, path):
        return self.operators.get(path)

    def execution_globals(self):
        return {"answer": 21}

    def start_debugpy(self, port):
        self.started.append(port)
        return {"ok": True, "port": port, "connected": False}


def _tree():
    script = FakeOp(
        "/project1/callbacks",
        family="DAT",
        op_type="executeDAT",
        text="def onFrameStart(frame):\n    return\n",
    )
    module = FakeOp(
        "/project1/mod1",
        family="DAT",
        op_type="textDAT",
        text="VALUE = 1\n",
        language="python",
    )
    glsl = FakeOp(
        "/project1/shader",
        family="DAT",
        op_type="textDAT",
        text="void main() {}",
        language="glsl",
    )
    broken = FakeOp(
        "/project1/broken",
        family="COMP",
        op_type="baseCOMP",
        errors=["Script error: name 'nope' is not defined"],
        pars=[FakePar("Speed", 1.5), FakePar("Bad", RuntimeError("cook failed"))],
    )
    project = FakeOp("/project1", children=[script, module, glsl, broken])
    root = FakeOp("/", children=[project])
    return FakeContext(
        {
            "/": root,
            "/project1": project,
            "/project1/callbacks": script,
            "/project1/mod1": module,
            "/project1/shader": glsl,
            "/project1/broken": broken,
        }
    )


def test_execute_expression_and_statement():
    ctx = _tree()
    expr = dispatch("execute_python", {"code": "answer + 1"}, ctx)
    assert expr == {
        "ok": True,
        "result": "22",
        "stdout": "",
        "stderr": "",
        "traceback": None,
    }
    statement = dispatch(
        "execute_python",
        {"code": "print('hi')\nvalue = answer"},
        ctx,
    )
    assert statement["ok"] is True
    assert statement["result"] is None
    assert statement["stdout"] == "hi\n"


def test_execute_traceback():
    result = dispatch("execute_python", {"code": "raise RuntimeError('boom')"}, _tree())
    assert result["ok"] is False
    assert "boom" in result["traceback"]


def test_execute_rejects_empty_code():
    result = dispatch("execute_python", {"code": "   "}, _tree())
    assert result["ok"] is False


def test_read_and_write_dat():
    ctx = _tree()
    read = dispatch("read_dat", {"path": "/project1/mod1"}, ctx)
    assert read["ok"] is True
    assert "VALUE = 1" in read["text"]
    written = dispatch("write_dat", {"path": "/project1/mod1", "text": "VALUE = 2\n"}, ctx)
    assert written["ok"] is True
    assert ctx.resolve("/project1/mod1").text == "VALUE = 2\n"


def test_read_rejects_non_dat():
    result = dispatch("read_dat", {"path": "/project1/broken"}, _tree())
    assert result["ok"] is False
    assert "not a text DAT" in result["error"]


def test_list_python_dats_skips_glsl_and_caps_results():
    ctx = _tree()
    listed = dispatch("list_python_dats", {"path": "/project1"}, ctx)
    paths = [item["path"] for item in listed["operators"]]
    assert paths == ["/project1/callbacks", "/project1/mod1"]
    assert listed["truncated"] is False
    capped = dispatch("list_python_dats", {"path": "/project1", "limit": 1}, ctx)
    assert len(capped["operators"]) == 1
    assert capped["truncated"] is True


def test_operator_errors_and_describe():
    ctx = _tree()
    errors = dispatch("operator_errors", {"path": "/project1"}, ctx)
    assert errors["operators"][0]["path"] == "/project1/broken"
    described = dispatch("describe_operator", {"path": "/project1/broken", "parameter_limit": 1}, ctx)
    assert described["op_type"] == "baseCOMP"
    assert described["errors"] == ["Script error: name 'nope' is not defined"]
    assert described["parameters"] == [{"name": "Speed", "value": "1.5"}]
    assert described["parameters_truncated"] is True
    full = dispatch("describe_operator", {"path": "/project1/broken"}, ctx)
    assert full["parameters"][1]["value"].startswith("<error:")


def test_missing_operator():
    result = dispatch("describe_operator", {"path": "/missing"}, _tree())
    assert result == {"ok": False, "error": "Operator not found: /missing"}


def test_unknown_method():
    result = dispatch("nope", {}, _tree())
    assert result["ok"] is False


def test_debugpy_missing_message_uses_touchdesigner_python():
    result = TouchDesignerContext(None).start_debugpy(5678)
    assert result["ok"] is False
    assert "debugpy is not installed" in result["error"]
    assert result["install"] == f'"{TD_PYTHON}" -m pip install debugpy'
