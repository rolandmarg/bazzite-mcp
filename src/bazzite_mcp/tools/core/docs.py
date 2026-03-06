import asyncio
import logging
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from mcp.server.fastmcp import Context

from bazzite_mcp.cache.docs_cache import DocsCache
from bazzite_mcp.config import load_config
from bazzite_mcp.runner import ToolError


logger = logging.getLogger(__name__)


def _extract_content(soup: BeautifulSoup) -> str | None:
    """Extract main content with multiple fallback selectors."""
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
            if len(text) > 50:
                return text

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
        if (
            parsed.netloc == parsed_base.netloc
            and not parsed.fragment
            and not parsed.path.startswith("/cdn-cgi/")
        ):
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
    report = await _refresh_docs_cache(ctx)
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


async def _query_bazzite_docs(query: str, ctx: Context | None = None) -> str:
    """Search cached Bazzite documentation using full-text search."""
    cache = DocsCache()
    cache, refresh_note = await _ensure_fresh_docs_cache(cache, ctx)

    if cache.page_count() == 0:
        return (
            "Docs cache is empty. Auto-refresh was attempted but no pages were cached."
            + refresh_note
        )

    results = cache.search(query, limit=10)

    if not results:
        return f"No results for '{query}' in cached docs." + refresh_note

    parts: list[str] = []
    for result in results:
        snippet = result["content"][:500]
        parts.append(
            f"### {result['title']} ({result['section']})\n{snippet}\nSource: {result['url']}"
        )
    return "\n\n---\n\n".join(parts) + refresh_note


async def _bazzite_changelog(version: str | None = None, count: int = 5) -> str:
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


async def _refresh_docs_cache(ctx: Context | None = None) -> str:
    """Crawl docs.bazzite.gg recursively and refresh the local cache."""
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
            path_parts = [part for part in parsed.path.strip("/").split("/") if part]
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
    else:
        errors.append("No docs pages were fetched; existing cache was preserved.")

    report = f"Refreshed docs cache: {fetched} pages crawled (max {max_pages})."
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


async def refresh_docs_cache(ctx: Context | None = None) -> str:
    """Public wrapper for docs cache refresh."""
    return await _refresh_docs_cache(ctx)


async def docs(
    action: Literal["search", "changelog", "refresh"],
    query: str | None = None,
    version: str | None = None,
    count: int = 5,
    ctx: Context | None = None,
) -> str:
    """Search docs, get changelogs, or refresh the docs cache."""
    if action == "search":
        if not query:
            raise ToolError("'query' is required for action='search'.")
        return await _query_bazzite_docs(query, ctx)
    if action == "changelog":
        return await _bazzite_changelog(version, count)
    if action == "refresh":
        return await _refresh_docs_cache(ctx)
    raise ToolError(f"Unknown action '{action}'.")
