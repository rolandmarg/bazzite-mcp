import asyncio

from bazzite_mcp.server import mcp


def test_server_exists() -> None:
    assert mcp is not None
    assert mcp.name == "bazzite"


def test_server_exposes_no_prompts() -> None:
    prompts = asyncio.run(mcp.list_prompts())
    assert prompts == []
