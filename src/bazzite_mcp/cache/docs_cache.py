from datetime import datetime, timedelta, timezone

from bazzite_mcp.config import load_config
from bazzite_mcp.db import ensure_tables, get_connection, get_db_path


class DocsCache:
    def __init__(self) -> None:
        db_path = get_db_path("docs_cache.db")
        self._conn = get_connection(db_path)
        ensure_tables(self._conn, "cache")

    def store_page(self, url: str, title: str, content: str, section: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO pages (url, title, content, section, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (url, title, content, section, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def store_changelog(self, version: str, date: str, body: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO changelogs (version, date, body) VALUES (?, ?, ?)",
            (version, date, body),
        )
        self._conn.commit()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT p.url, p.title, p.content, p.section, p.fetched_at "
            "FROM pages p JOIN pages_fts f ON p.id = f.rowid "
            "WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_changelog(self, version: str | None = None, limit: int = 5) -> list[dict]:
        if version:
            rows = self._conn.execute(
                "SELECT * FROM changelogs WHERE version = ?", (version,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM changelogs ORDER BY date DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def is_stale(self) -> bool:
        row = self._conn.execute("SELECT MIN(fetched_at) AS oldest FROM pages").fetchone()
        if not row or not row["oldest"]:
            return True

        oldest_raw = str(row["oldest"])
        if oldest_raw.endswith("Z"):
            oldest_raw = oldest_raw.replace("Z", "+00:00")
        oldest = datetime.fromisoformat(oldest_raw)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - oldest > timedelta(days=load_config().cache_ttl_days)

    def clear(self) -> None:
        self._conn.execute("DELETE FROM pages")
        self._conn.execute("DELETE FROM pages_fts")
        self._conn.commit()

    def page_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS count FROM pages").fetchone()
        return int(row["count"]) if row else 0
