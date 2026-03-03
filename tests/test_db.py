from bazzite_mcp.db import ensure_tables, get_connection, get_db_path


def test_get_db_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = get_db_path("test.db")
    assert path == tmp_path / "bazzite-mcp" / "test.db"
    assert path.parent.exists()


def test_ensure_audit_table(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("audit.db")
    conn = get_connection(db_path)
    ensure_tables(conn, "audit")
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='actions'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_ensure_cache_tables(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("cache.db")
    conn = get_connection(db_path)
    ensure_tables(conn, "cache")
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pages'"
    )
    assert cursor.fetchone() is not None
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='changelogs'"
    )
    assert cursor.fetchone() is not None
    conn.close()
