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


def test_get_connection_enables_foreign_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("fk.db")
    conn = get_connection(db_path)
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    conn.close()
    assert row is not None
    assert int(row[0]) == 1


def test_migrates_embeddings_model_column_for_old_cache_schema(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("docs_cache.db")
    conn = get_connection(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT,
            content TEXT,
            section TEXT,
            fetched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            chunk_text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            dimensions INTEGER NOT NULL,
            FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE,
            UNIQUE(page_id, chunk_index)
        );
        """
    )
    conn.commit()
    conn.close()

    from bazzite_mcp.cache.docs_cache import DocsCache

    cache = DocsCache()
    cols = {
        str(row["name"])
        for row in cache._conn.execute("PRAGMA table_info(embeddings)").fetchall()
    }
    cache.close()
    assert "model" in cols
