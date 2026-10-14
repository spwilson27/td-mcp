import asyncio

from td_mcp.server import mcp


def test_debug_tools_are_registered():
    tools = asyncio.run(mcp.list_tools())
    assert sorted(tool.name for tool in tools) == [
        "describe_operator",
        "execute_python",
        "list_python_dats",
        "operator_errors",
        "read_dat",
        "start_debugpy",
        "td_status",
        "write_dat",
    ]
