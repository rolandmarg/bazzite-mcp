from bazzite_mcp.server import mcp


def test_server_exists() -> None:
    assert mcp is not None
    assert mcp.name == "bazzite"
