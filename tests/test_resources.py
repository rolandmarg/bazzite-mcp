from bazzite_mcp.resources import (
    get_install_policy,
    get_knowledge_index,
    get_server_info,
    get_system_overview,
)


def test_server_info_contains_metadata():
    result = get_server_info()
    assert "bazzite-mcp" in result
    assert "Docs mode" in result
    assert "Official docs" in result


def test_system_overview_contains_system_data():
    result = get_system_overview()
    assert result.strip()


def test_knowledge_index_contains_resources_and_sources() -> None:
    result = get_knowledge_index()
    assert "bazzite://knowledge/install-policy" in result
    assert "bazzite://knowledge/troubleshooting" in result
    assert "https://docs.bazzite.gg" in result


def test_install_policy_resource_contains_heading() -> None:
    result = get_install_policy()
    assert result.startswith("# Install Policy")
    assert "rpm-ostree" in result
