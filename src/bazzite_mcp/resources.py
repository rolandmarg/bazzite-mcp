"""MCP resources — read-only context for AI agents."""

from bazzite_mcp import __version__
from bazzite_mcp.cache.docs_cache import DocsCache
from bazzite_mcp.config import load_config
from bazzite_mcp.tools.docs import _install_policy
from bazzite_mcp.tools.packages import INSTALL_POLICY
from bazzite_mcp.tools.system import _system_info_basic


def get_system_overview() -> str:
    """Current system info snapshot."""
    return _system_info_basic()


def get_install_hierarchy() -> str:
    """Bazzite's 6-tier install hierarchy with explanations."""
    tiers = ["gui", "cli", "service", "dev-environment", "driver", "android"]
    parts = [
        "# Bazzite Install Hierarchy\n",
        "General order: ujust > flatpak > brew > distrobox/quadlet > AppImage > rpm-ostree\n",
    ]
    for tier in tiers:
        parts.append(f"## {tier}\n{_install_policy(tier)}\n")
    return "\n".join(parts)


def get_install_policy_resource() -> str:
    """Quick-reference install policy string."""
    return INSTALL_POLICY


def get_docs_index() -> str:
    """Index of all cached documentation pages."""
    cache = DocsCache()
    if cache.page_count() == 0:
        return "Docs cache is empty. Call docs(action='refresh') to populate."

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
    cache = DocsCache()
    return (
        f"# bazzite-mcp v{__version__}\n\n"
        f"Docs source: {cfg.docs_base_url}\n"
        f"Cache TTL: {cfg.cache_ttl_seconds() // 3600} hours\n"
        f"Max crawl pages: {cfg.crawl_max_pages}\n"
        f"Cached pages: {cache.page_count()}\n"
        f"Cache stale: {cache.is_stale()}\n"
    )
