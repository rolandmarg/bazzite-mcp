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
        "SELECT name FROM sqlite_master WHERE type='table' AND name='game_reports'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_get_connection_enables_foreign_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("fk.db")
    conn = get_connection(db_path)
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    conn.close()
    assert row is not None
    assert int(row[0]) == 1


def test_get_connection_read_only_opens_existing_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("readonly.db")
    conn = get_connection(db_path)
    conn.execute("CREATE TABLE sample (value TEXT)")
    conn.execute("INSERT INTO sample (value) VALUES ('ok')")
    conn.commit()
    conn.close()

    db_path.chmod(0o444)
    db_path.parent.chmod(0o555)
    try:
        read_only_conn = get_connection(db_path, read_only=True)
        row = read_only_conn.execute("SELECT value FROM sample").fetchone()
        read_only_conn.close()
    finally:
        db_path.parent.chmod(0o755)
        db_path.chmod(0o644)

    assert row is not None
    assert row["value"] == "ok"
