from bazzite_mcp.cache.docs_cache import DocsCache


def test_store_and_search(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/test",
        title="Test Page",
        content="Flatpak is the primary method for installing GUI applications on Bazzite.",
        section="Installing Software",
    )
    results = cache.search("flatpak gui")
    assert len(results) > 0
    assert "flatpak" in results[0]["content"].lower()


def test_cache_staleness(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/old",
        title="Old Page",
        content="Old content",
        section="Test",
    )
    cache._conn.execute("UPDATE pages SET fetched_at = '2020-01-01T00:00:00Z'")
    cache._conn.commit()
    assert cache.is_stale() is True
