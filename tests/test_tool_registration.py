import asyncio

from bazzite_mcp.server import mcp


def test_all_tools_registered() -> None:
    assert mcp is not None
    assert mcp.name == "bazzite"


def test_server_resources_exclude_policy_uris() -> None:
    resources = asyncio.run(mcp.list_resources())
    uris = {str(resource.uri) for resource in resources}
    assert "bazzite://install/hierarchy" not in uris
    assert "bazzite://install/policy" not in uris
    assert "bazzite://knowledge/index" in uris
    assert "bazzite://knowledge/install-policy" in uris
