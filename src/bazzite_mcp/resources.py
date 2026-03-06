"""MCP resources — read-only context for AI agents."""

import sqlite3

from bazzite_mcp import __version__
from bazzite_mcp.cache.docs_cache import DocsCache
from bazzite_mcp.config import load_config
from bazzite_mcp.db import get_db_path
from bazzite_mcp.tools.system import _system_info_basic


def _open_docs_cache_read_only() -> DocsCache | None:
    db_path = get_db_path("docs_cache.db", create_dir=False)
    if not db_path.exists():
        return None

    try:
        return DocsCache(read_only=True)
    except sqlite3.Error:
        return None


def get_system_overview() -> str:
    """Current system info snapshot."""
    return _system_info_basic()


def get_docs_index() -> str:
    """Index of all cached documentation pages."""
    cache = _open_docs_cache_read_only()
    if cache is None or cache.page_count() == 0:
        return "Docs cache is empty. Call docs(action='refresh') to populate."

    with cache:
        rows = cache._conn.execute(
            "SELECT url, title, section FROM pages ORDER BY section, title"
        ).fetchall()
        parts = [f"# Cached Bazzite Docs ({len(rows)} pages)\n"]
        current_section = ""
        for row in rows:
            if row["section"] != current_section:
                current_section = row["section"]
                parts.append(f"\n## {current_section}")
            parts.append(f"- [{row['title']}]({row['url']})")
        return "\n".join(parts)


def get_server_info() -> str:
    """bazzite-mcp server metadata."""
    cfg = load_config()
    cache = _open_docs_cache_read_only()
    cached_pages = 0
    cache_stale = True
    if cache is not None:
        with cache:
            cached_pages = cache.page_count()
            cache_stale = cache.is_stale()
    return (
        f"# bazzite-mcp v{__version__}\n\n"
        f"Docs source: {cfg.docs_base_url}\n"
        f"Cache TTL: {cfg.cache_ttl_seconds() // 3600} hours\n"
        f"Max crawl pages: {cfg.crawl_max_pages}\n"
        f"Cached pages: {cached_pages}\n"
        f"Cache stale: {cache_stale}\n"
    )
