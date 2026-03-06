from bazzite_mcp.cache.docs_cache import DocsCache
from bazzite_mcp.resources import get_server_info, get_system_overview


def test_server_info_contains_metadata():
    result = get_server_info()
    assert "bazzite-mcp" in result
    assert "Cache TTL" in result
    assert "Cached pages" in result


def test_system_overview_contains_system_data():
    result = get_system_overview()
    assert result.strip()


def test_server_info_reads_existing_read_only_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/test",
        title="Test Page",
        content="Docs content",
        section="Test",
    )
    cache.close()

    db_path = tmp_path / "bazzite-mcp" / "docs_cache.db"
    db_path.chmod(0o444)
    db_path.parent.chmod(0o555)
    try:
        result = get_server_info()
    finally:
        db_path.parent.chmod(0o755)
        db_path.chmod(0o644)

    assert "Cached pages: 1" in result
