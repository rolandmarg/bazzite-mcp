import os
import sqlite3
from pathlib import Path
from urllib.parse import quote


def get_db_path(filename: str, *, create_dir: bool = True) -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    db_dir = data_home / "bazzite-mcp"
    if create_dir:
        db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / filename


def get_connection(db_path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(
            f"file:{quote(str(db_path), safe='/')}?mode=ro&immutable=1",
            uri=True,
        )
    else:
        conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
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
CREATE TABLE IF NOT EXISTS game_reports (
    app_id INTEGER PRIMARY KEY,
    protondb_summary TEXT,
    pcgamingwiki_data TEXT,
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


def ensure_tables(conn: sqlite3.Connection, db_type: str) -> None:
    if db_type == "audit":
        conn.executescript(AUDIT_SCHEMA)
    elif db_type == "cache":
        conn.executescript(CACHE_SCHEMA)
    conn.commit()
