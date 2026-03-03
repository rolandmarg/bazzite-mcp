import os
import sqlite3
from pathlib import Path


def get_db_path(filename: str) -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    db_dir = data_home / "bazzite-mcp"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / filename


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    tool TEXT NOT NULL,
    command TEXT NOT NULL,
    args TEXT,
    result TEXT,
    output TEXT,
    rollback TEXT,
    client TEXT
);
"""


CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    content TEXT,
    section TEXT,
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    title, content, section, content='pages', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, title, content, section)
    VALUES (new.id, new.title, new.content, new.section);
END;

CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, content, section)
    VALUES ('delete', old.id, old.title, old.content, old.section);
END;

CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, content, section)
    VALUES ('delete', old.id, old.title, old.content, old.section);
    INSERT INTO pages_fts(rowid, title, content, section)
    VALUES (new.id, new.title, new.content, new.section);
END;

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

CREATE TABLE IF NOT EXISTS changelogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    date TEXT,
    body TEXT
);
"""


def ensure_tables(conn: sqlite3.Connection, db_type: str) -> None:
    if db_type == "audit":
        conn.executescript(AUDIT_SCHEMA)
    elif db_type == "cache":
        conn.executescript(CACHE_SCHEMA)
    conn.commit()
