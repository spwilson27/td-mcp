"""stdio MCP server that forwards debug tools to TouchDesigner."""

from __future__ import annotations

from mcp.server import MCPServer

from td_mcp.client import call

mcp = MCPServer(
    "td-python-debug",
    instructions=(
        "Tools for debugging Python inside a running TouchDesigner process. "
        "execute_python runs on the main thread and returns stdout plus any traceback. "
        "read_dat, write_dat, list_python_dats, operator_errors, and describe_operator "
        "inspect the network. start_debugpy listens on 127.0.0.1 without pausing "
        "TouchDesigner. If a tool says TouchDesigner is not reachable, a project with the "
        "debug component is not open, or it did not start."
    ),
)


@mcp.tool()
def td_status() -> dict:
    """Report whether TouchDesigner is reachable and which Python it is running."""
    return call("td_status")


@mcp.tool()
def execute_python(code: str, timeout: float = 30) -> dict:
    """Run Python on TouchDesigner's main thread.

    Expressions return a result. Statements return stdout. Failures include a traceback.
    timeout is how long to wait for the main thread, in seconds. The running code is not interrupted.
    """
    return call("execute_python", {"code": code}, timeout=timeout)


@mcp.tool()
def read_dat(path: str) -> dict:
    """Read the text of a DAT. path is an operator path such as /project1/script1."""
    return call("read_dat", {"path": path})


@mcp.tool()
def write_dat(path: str, text: str) -> dict:
    """Replace the text of a script DAT."""
    return call("write_dat", {"path": path, "text": text})


@mcp.tool()
def list_python_dats(path: str = "/", max_depth: int = 4, limit: int = 50) -> dict:
    """List Python DATs under a path."""
    return call(
        "list_python_dats",
        {"path": path, "max_depth": max_depth, "limit": limit},
    )


@mcp.tool()
def operator_errors(path: str = "/", max_depth: int = 4, limit: int = 50) -> dict:
    """List operators that currently have errors, warnings, or script errors."""
    return call(
        "operator_errors",
        {"path": path, "max_depth": max_depth, "limit": limit},
    )


@mcp.tool()
def describe_operator(path: str, parameter_limit: int = 40) -> dict:
    """Describe an operator's type, errors, and parameters."""
    return call(
        "describe_operator",
        {"path": path, "parameter_limit": parameter_limit},
    )


@mcp.tool()
def start_debugpy(port: int = 5678) -> dict:
    """Start debugpy inside TouchDesigner without pausing the UI.

    Listens on 127.0.0.1 at the given port. If debugpy is missing, the result
    includes the pip command for TouchDesigner's Python.
    """
    return call("start_debugpy", {"port": port})


def main() -> None:
    mcp.run()
