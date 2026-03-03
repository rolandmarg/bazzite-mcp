from bazzite_mcp.resources import get_install_hierarchy, get_server_info


def test_install_hierarchy_contains_tiers():
    result = get_install_hierarchy()
    assert "Flatpak" in result
    assert "Homebrew" in result
    assert "Distrobox" in result
    assert "rpm-ostree" in result


def test_server_info_contains_metadata():
    result = get_server_info()
    assert "bazzite-mcp" in result
    assert "Cache TTL" in result
    assert "Cached pages" in result
