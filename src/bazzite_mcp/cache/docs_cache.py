import re
from datetime import datetime, timezone

from bazzite_mcp.config import load_config
from bazzite_mcp.db import (
    ensure_tables,
    get_connection,
    get_db_path,
    migrate_cache_schema,
)


SYNONYMS: dict[str, list[str]] = {
    "browser": ["firefox", "chromium", "brave"],
    "sandbox": ["flatpak", "permissions", "flatseal"],
    "gamepad": ["controller", "joystick", "gamecontroller"],
    "update": ["upgrade", "rebase", "rpm-ostree"],
}


def _sanitize_fts5_query(query: str) -> str:
    """Sanitize a query for FTS5 MATCH to prevent syntax errors.

    Extracts words and quotes each as a literal term, stripping FTS5
    operators (OR, NOT, NEAR, *, etc.) that could cause crashes.
    """
    words = re.findall(r"\w+", query)
    if not words:
        return '""'
    return " ".join(f'"{w}"' for w in words)


def _expand_fts5_query(query: str) -> str:
    """Expand query terms with Bazzite-specific synonyms for better recall."""
    words = re.findall(r"\w+", query)
    if not words:
        return '""'

    groups: list[str] = []
    for raw in words:
        terms = [raw]
        terms.extend(SYNONYMS.get(raw.lower(), [])[:3])

        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            lowered = term.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(term)

        if len(deduped) == 1:
            groups.append(f'"{deduped[0]}"')
        else:
            groups.append("(" + " OR ".join(f'"{term}"' for term in deduped) + ")")

    return " AND ".join(groups)


class DocsCache:
    def __init__(self) -> None:
        db_path = get_db_path("docs_cache.db")
        self._conn = get_connection(db_path)
        ensure_tables(self._conn, "cache")
        migrate_cache_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "DocsCache":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

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
        return self.search_scored(query, limit=limit)

    def search_scored(self, query: str, limit: int = 20) -> list[dict]:
        expanded_query = _expand_fts5_query(query)
        rows = self._conn.execute(
            "SELECT p.url, p.title, p.content, p.section, p.fetched_at, "
            "bm25(pages_fts) AS keyword_score "
            "FROM pages p JOIN pages_fts f ON p.id = f.rowid "
            "WHERE pages_fts MATCH ? ORDER BY keyword_score LIMIT ?",
            (expanded_query, limit),
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
        row = self._conn.execute(
            "SELECT MIN(fetched_at) AS oldest FROM pages"
        ).fetchone()
        if not row or not row["oldest"]:
            return True

        oldest_raw = str(row["oldest"])
        if oldest_raw.endswith("Z"):
            oldest_raw = oldest_raw.replace("Z", "+00:00")
        oldest = datetime.fromisoformat(oldest_raw)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        ttl_seconds = load_config().cache_ttl_seconds()
        return (datetime.now(timezone.utc) - oldest).total_seconds() > ttl_seconds

    def clear(self) -> None:
        self._conn.execute("DELETE FROM embeddings")
        self._conn.execute("DELETE FROM pages")
        self._conn.execute("DELETE FROM pages_fts")
        self._conn.commit()

    def page_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS count FROM pages").fetchone()
        return int(row["count"]) if row else 0
