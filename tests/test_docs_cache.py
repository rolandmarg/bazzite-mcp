from bazzite_mcp.cache.docs_cache import DocsCache, _sanitize_fts5_query


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


# --- FTS5 query sanitization ---


def test_fts5_sanitize_normal_query() -> None:
    assert _sanitize_fts5_query("flatpak gui") == '"flatpak" "gui"'


def test_fts5_sanitize_strips_operators() -> None:
    result = _sanitize_fts5_query('foo OR bar NOT "baz"')
    assert "OR" not in result or '"OR"' in result
    assert '"foo"' in result
    assert '"bar"' in result


def test_fts5_sanitize_empty_query() -> None:
    assert _sanitize_fts5_query("") == '""'


def test_fts5_sanitize_special_chars() -> None:
    result = _sanitize_fts5_query("test* AND (foo)")
    assert '"test"' in result
    assert '"AND"' in result
    assert '"foo"' in result


def test_search_with_injection_attempt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/test",
        title="Test",
        content="Test content for safety",
        section="Test",
    )
    # Should not crash with FTS5 special syntax
    results = cache.search('* OR "injection" NEAR/5')
    # May return results or empty, but should not raise
    assert isinstance(results, list)


def test_search_expands_synonyms(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/flatpak-permissions",
        title="Flatpak Permissions",
        content="Use Flatseal to manage Flatpak permissions for Firefox.",
        section="Installing_and_Managing_Software",
    )

    results = cache.search("browser sandbox")
    assert len(results) > 0
    assert "Flatpak" in results[0]["title"]


def test_is_stale_accepts_z_suffix_timestamp(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/fresh-z",
        title="Fresh Z",
        content="Fresh content",
        section="Test",
    )
    cache._conn.execute(
        "UPDATE pages SET fetched_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
    )
    cache._conn.commit()
    assert cache.is_stale() is False


def test_is_stale_accepts_offset_timestamp(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/fresh-offset",
        title="Fresh Offset",
        content="Fresh content",
        section="Test",
    )
    cache._conn.execute(
        "UPDATE pages SET fetched_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')"
    )
    cache._conn.commit()
    assert cache.is_stale() is False


def test_is_stale_accepts_naive_timestamp(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/fresh-naive",
        title="Fresh Naive",
        content="Fresh content",
        section="Test",
    )
    cache._conn.execute(
        "UPDATE pages SET fetched_at = strftime('%Y-%m-%dT%H:%M:%S', 'now')"
    )
    cache._conn.commit()
    assert cache.is_stale() is False
