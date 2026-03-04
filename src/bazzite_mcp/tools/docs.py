import re
import asyncio
import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from mcp.server.fastmcp import Context

from bazzite_mcp.cache.docs_cache import DocsCache
from bazzite_mcp.cache.embeddings import embed_pages, semantic_search
from bazzite_mcp.config import load_config
from bazzite_mcp.runner import ToolError


logger = logging.getLogger(__name__)


def _extract_content(soup: BeautifulSoup) -> str | None:
    """Extract main content with multiple fallback selectors."""
    # mkdocs-material selectors (most likely for docs.bazzite.gg)
    selectors = [
        ("article", {}),
        (None, {"class_": "md-content"}),
        (None, {"class_": "md-content__inner"}),
        ("main", {}),
        (None, {"role": "main"}),
        (None, {"id": "content"}),
    ]
    for tag, attrs in selectors:
        el = soup.find(tag, **attrs) if tag else soup.find(**attrs)
        if el and isinstance(el, Tag):
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 50:  # skip near-empty matches
                return text

    # Last resort: extract body minus nav/header/footer
    body = soup.find("body")
    if body and isinstance(body, Tag):
        for unwanted in body.find_all(["nav", "header", "footer", "script", "style"]):
            unwanted.decompose()
        text = body.get_text(separator="\n", strip=True)
        if len(text) > 50:
            return text

    return None


def _discover_doc_links(soup: BeautifulSoup, base_url: str) -> set[str]:
    """Find all internal doc links on a page."""
    cfg = load_config()
    parsed_base = urlparse(cfg.docs_base_url)
    links: set[str] = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href")
        if not isinstance(href, str):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        # Only follow links within docs.bazzite.gg, skip anchors/external/CDN
        if (
            parsed.netloc == parsed_base.netloc
            and not parsed.fragment
            and not parsed.path.startswith("/cdn-cgi/")
        ):
            # Normalize: strip query params, ensure trailing slash for dirs
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if not clean.endswith("/") and "." not in parsed.path.split("/")[-1]:
                clean += "/"
            links.add(clean)
    return links


async def _ensure_fresh_docs_cache(
    cache: DocsCache, ctx: Context | None = None
) -> tuple[DocsCache, str]:
    """Refresh docs on demand when cache is empty or stale."""
    reason = ""
    if cache.page_count() == 0:
        reason = "empty"
    elif cache.is_stale():
        reason = "stale"

    if not reason:
        return cache, ""

    logger.info("Docs cache %s; triggering auto-refresh", reason)
    report = await refresh_docs_cache(ctx)
    refreshed_cache = DocsCache()
    if refreshed_cache.page_count() == 0:
        return refreshed_cache, (
            "\n\nNote: auto-refresh ran but docs cache is still empty. "
            f"Refresh report: {report.splitlines()[0]}"
        )

    return refreshed_cache, (
        f"\n\nNote: auto-refreshed docs cache ({reason} cache). "
        f"{report.splitlines()[0]}"
    )


def reciprocal_rank_fusion(
    keyword_results: list[dict],
    semantic_results: list[dict],
    k: int = 60,
    limit: int = 10,
) -> list[dict]:
    """Fuse keyword and semantic rankings with reciprocal rank fusion."""
    fused_scores: dict[str, float] = {}
    merged: dict[str, dict] = {}
    keyword_urls: set[str] = set()
    semantic_urls: set[str] = set()

    for rank, result in enumerate(keyword_results):
        url = str(result.get("url", ""))
        if not url:
            continue
        keyword_urls.add(url)
        fused_scores[url] = fused_scores.get(url, 0.0) + 1.0 / (k + rank + 1)
        merged[url] = dict(result)

    for rank, result in enumerate(semantic_results):
        url = str(result.get("url", ""))
        if not url:
            continue
        semantic_urls.add(url)
        fused_scores[url] = fused_scores.get(url, 0.0) + 1.0 / (k + rank + 1)
        if url not in merged:
            merged[url] = dict(result)
            continue

        if len(str(result.get("content", ""))) > len(
            str(merged[url].get("content", ""))
        ):
            merged[url]["content"] = result.get("content", "")
        if "score" in result:
            merged[url]["semantic_score"] = result["score"]

    ranked_urls = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
    fused: list[dict] = []
    for url, score in ranked_urls[:limit]:
        item = dict(merged[url])
        item["fused_score"] = round(score, 6)
        if url in keyword_urls and url in semantic_urls:
            item["search_mode"] = "hybrid"
        elif url in semantic_urls:
            item["search_mode"] = "semantic"
        else:
            item["search_mode"] = "keyword"
        fused.append(item)
    return fused


async def query_bazzite_docs(query: str, ctx: Context | None = None) -> str:
    """Keyword search over cached Bazzite documentation (FTS5).

    Best for: exact terms, command names, package names, error messages.
    Use semantic_search_docs instead for natural language questions.
    Auto-refreshes cache when empty or stale.
    """
    cache = DocsCache()
    cache, refresh_note = await _ensure_fresh_docs_cache(cache, ctx)

    if cache.page_count() == 0:
        return (
            "Docs cache is empty. Auto-refresh was attempted but no pages were cached."
            + refresh_note
        )

    keyword_results = cache.search_scored(query, limit=20)
    semantic_results = await semantic_search(cache._conn, query, limit=20)

    if semantic_results:
        results = reciprocal_rank_fusion(keyword_results, semantic_results, limit=10)
    else:
        results = keyword_results[:10]

    if not results:
        return f"No results for '{query}' in cached docs."

    parts: list[str] = []
    for result in results:
        snippet = result["content"][:500]
        score_suffix = ""
        if "fused_score" in result:
            score_suffix = (
                f" [{result.get('search_mode', 'hybrid')}: {result['fused_score']}]"
            )
        parts.append(
            f"### {result['title']} ({result['section']}){score_suffix}\n{snippet}\nSource: {result['url']}"
        )
    return "\n\n---\n\n".join(parts) + refresh_note


async def semantic_search_docs(
    query: str, limit: int = 5, ctx: Context | None = None
) -> str:
    """Semantic similarity search over cached Bazzite docs using AI embeddings.

    Best for: natural language questions where exact keywords may not match
    (e.g. 'how to run android apps' finds Waydroid docs).
    Use query_bazzite_docs instead for exact keyword/command name lookups.
    Falls back to keyword search if embeddings are unavailable.
    """
    cache = DocsCache()
    cache, refresh_note = await _ensure_fresh_docs_cache(cache, ctx)

    if cache.page_count() == 0:
        return (
            "Docs cache is empty. Auto-refresh was attempted but no pages were cached."
            + refresh_note
        )

    results = await semantic_search(cache._conn, query, limit=limit)
    if not results:
        # Fall back to keyword search
        fallback = cache.search(query)
        if not fallback:
            return f"No results for '{query}' in cached docs." + refresh_note
        parts: list[str] = []
        for r in fallback:
            snippet = r["content"][:500]
            parts.append(
                f"### {r['title']} ({r['section']})\n{snippet}\nSource: {r['url']}"
            )
        return "\n\n---\n\n".join(parts) + refresh_note

    parts: list[str] = []
    for r in results:
        snippet = r["content"][:500]
        parts.append(
            f"### {r['title']} ({r['section']}) [score: {r['score']}]\n"
            f"{snippet}\nSource: {r['url']}"
        )
    return "\n\n---\n\n".join(parts) + refresh_note


async def bazzite_changelog(version: str | None = None, count: int = 5) -> str:
    """Get Bazzite release changelog from cache or GitHub API."""
    cfg = load_config()
    cache = DocsCache()
    entries = cache.get_changelog(version=version, limit=count)
    if entries:
        return "\n\n".join(
            f"## {entry['version']} ({entry['date']})\n{entry['body'][:1000]}"
            for entry in entries
        )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                cfg.github_releases_url, params={"per_page": count}
            )
            response.raise_for_status()
            releases = response.json()
    except Exception as exc:
        raise ToolError(f"Failed to fetch changelogs: {exc}") from exc

    parts: list[str] = []
    for release in releases:
        tag = release.get("tag_name", "unknown")
        published = release.get("published_at", "unknown")
        body = release.get("body", "")
        cache.store_changelog(tag, published, body)
        parts.append(f"## {tag} ({published})\n{body[:1000] if body else 'No body'}")
    return "\n\n".join(parts)


def install_policy(app_type: str) -> str:
    """Explain recommended install method by app type."""
    policies = {
        "gui": (
            "For GUI applications, use Flatpak (Tier 2).\n"
            "Install via Bazaar app store or: flatpak install flathub <app-id>\n"
            "Flatpak apps are sandboxed and update independently of the OS."
        ),
        "cli": (
            "For CLI/TUI tools, use Homebrew (Tier 3).\n"
            "Install via: brew install <package>\n"
            "Homebrew installs to user-space and avoids immutable host changes."
        ),
        "service": (
            "For persistent services, use Quadlet (Tier 4).\n"
            "Quadlet combines systemd + podman for declarative container services."
        ),
        "dev-environment": (
            "For development environments, use Distrobox (Tier 4).\n"
            "Example:\n  distrobox create --name dev --image ubuntu:24.04\n  distrobox enter dev"
        ),
        "driver": (
            "For drivers and kernel-adjacent packages, rpm-ostree is Tier 6 (last resort).\n"
            "Use only when no alternative exists; it can block updates/rebases."
        ),
        "android": ("For Android apps, use Waydroid.\nSetup via: ujust setup-waydroid"),
    }

    if app_type not in policies:
        supported = ", ".join(policies.keys())
        raise ToolError(
            f"Unknown app type '{app_type}'. Supported: {supported}.\n\n"
            "General hierarchy: ujust > flatpak > brew > distrobox > AppImage > rpm-ostree"
        )
    return policies[app_type]


async def refresh_docs_cache(ctx: Context | None = None) -> str:
    """Crawl docs.bazzite.gg recursively and refresh the local cache.

    Discovers all pages by following internal links starting from the homepage.
    Also fetches recent changelogs from GitHub releases.
    Uses multiple CSS selector fallbacks for robust content extraction.
    """
    cfg = load_config()
    cache = DocsCache()
    logger.info("Starting docs cache refresh (max_pages=%s)", cfg.crawl_max_pages)

    fetched = 0
    errors: list[str] = []
    staged_pages: list[dict[str, str]] = []
    visited: set[str] = set()
    to_visit: set[str] = {cfg.docs_base_url + "/"}
    max_pages = cfg.crawl_max_pages
    concurrency = 5
    sem = asyncio.Semaphore(concurrency)

    async def fetch_one(client: httpx.AsyncClient, url: str) -> dict:
        async with sem:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except Exception as exc:
                return {"url": url, "error": str(exc), "links": set(), "page": None}

            soup = BeautifulSoup(response.text, "html.parser")
            links = _discover_doc_links(soup, url)

            content = _extract_content(soup)
            if not content:
                return {
                    "url": url,
                    "error": "no extractable content",
                    "links": links,
                    "page": None,
                }

            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else url

            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            section = "/".join(path_parts) if path_parts else "Home"

            return {
                "url": url,
                "error": None,
                "links": links,
                "page": {
                    "url": url,
                    "title": title,
                    "content": content,
                    "section": section,
                },
            }

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        while to_visit and fetched < max_pages:
            batch: list[str] = []
            while to_visit and len(batch) < concurrency:
                url = to_visit.pop()
                if url in visited:
                    continue
                visited.add(url)
                batch.append(url)

            if not batch:
                continue

            results = await asyncio.gather(*(fetch_one(client, url) for url in batch))
            for result in results:
                links = result.get("links", set())
                if isinstance(links, set):
                    to_visit.update(links - visited)

                page = result.get("page")
                if isinstance(page, dict):
                    staged_pages.append(
                        {
                            "url": str(page["url"]),
                            "title": str(page["title"]),
                            "content": str(page["content"]),
                            "section": str(page["section"]),
                        }
                    )
                    fetched += 1
                    if ctx:
                        await ctx.report_progress(fetched, max_pages)
                    if fetched >= max_pages:
                        break
                else:
                    errors.append(
                        f"{result.get('url', 'unknown')}: {result.get('error', 'unknown error')}"
                    )

            if fetched >= max_pages:
                break

    # Fetch changelogs from GitHub
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                cfg.github_releases_url, params={"per_page": 10}
            )
            response.raise_for_status()
            for release in response.json():
                cache.store_changelog(
                    release.get("tag_name", "unknown"),
                    release.get("published_at", ""),
                    release.get("body", ""),
                )
    except Exception as exc:
        errors.append(f"GitHub releases: {exc}")
        logger.warning("Failed to refresh changelogs: %s", exc)

    if staged_pages:
        cache.clear()
        for page in staged_pages:
            cache.store_page(
                url=page["url"],
                title=page["title"],
                content=page["content"],
                section=page["section"],
            )
        embedded, embed_errors = await embed_pages(cache._conn)
        errors.extend(embed_errors)
    else:
        embedded = 0
        embed_errors = []
        errors.append("No docs pages were fetched; existing cache was preserved.")

    report = f"Refreshed docs cache: {fetched} pages crawled (max {max_pages})."
    if embedded:
        report += f"\nEmbeddings: {embedded} chunks embedded for semantic search."
    elif not embed_errors:
        report += "\nEmbeddings: skipped (no new pages to embed)."
    if errors:
        logger.warning("Docs cache refresh completed with %s errors", len(errors))
        report += f"\n\nErrors ({len(errors)}):\n" + "\n".join(
            f"  - {err}" for err in errors
        )
    logger.info(
        "Docs cache refresh completed: fetched=%s visited=%s", fetched, len(visited)
    )
    report += f"\nSkipped {len(visited) - fetched} pages (no content or errors)."
    return report
