from bazzite_mcp.server import mcp


def test_all_tools_registered() -> None:
    assert mcp is not None
    assert mcp.name == "bazzite"
