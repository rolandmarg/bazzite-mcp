import httpx
from bs4 import BeautifulSoup

from bazzite_mcp.cache.docs_cache import DocsCache


DOCS_BASE = "https://docs.bazzite.gg"
GITHUB_API = "https://api.github.com/repos/ublue-os/bazzite/releases"

DOC_PAGES = [
    "/",
    "/Installing_and_Managing_Software/",
    "/Installing_and_Managing_Software/Flatpak/",
    "/Installing_and_Managing_Software/Homebrew/",
    "/Installing_and_Managing_Software/rpm-ostree/",
    "/Installing_and_Managing_Software/Updates_Rollbacks_and_Rebasing/",
    "/General/",
    "/Advanced/",
    "/FAQ/",
]


def query_bazzite_docs(query: str) -> str:
    """Full-text search cached Bazzite docs."""
    cache = DocsCache()
    if cache.page_count() == 0:
        return "Docs cache is empty. Run refresh_docs_cache() to populate it from docs.bazzite.gg."

    results = cache.search(query)
    if not results:
        return f"No results for '{query}' in cached docs."

    stale_notice = (
        "\n\nNote: cache may be stale; consider running refresh_docs_cache()."
        if cache.is_stale()
        else ""
    )

    parts: list[str] = []
    for result in results:
        snippet = result["content"][:500]
        parts.append(
            f"### {result['title']} ({result['section']})\n{snippet}\nSource: {result['url']}"
        )
    return "\n\n---\n\n".join(parts) + stale_notice


def bazzite_changelog(version: str | None = None, count: int = 5) -> str:
    """Get Bazzite release changelog from cache or GitHub API."""
    cache = DocsCache()
    entries = cache.get_changelog(version=version, limit=count)
    if entries:
        return "\n\n".join(
            f"## {entry['version']} ({entry['date']})\n{entry['body'][:1000]}"
            for entry in entries
        )

    try:
        response = httpx.get(GITHUB_API, params={"per_page": count}, timeout=15)
        response.raise_for_status()
        releases = response.json()
    except Exception as exc:  # noqa: BLE001
        return f"Failed to fetch changelogs: {exc}"

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
        "android": (
            "For Android apps, use Waydroid.\n"
            "Setup via: ujust setup-waydroid"
        ),
    }

    if app_type not in policies:
        supported = ", ".join(policies.keys())
        return (
            f"Unknown app type '{app_type}'. Supported: {supported}.\n\n"
            "General hierarchy: ujust > flatpak > brew > distrobox > AppImage > rpm-ostree"
        )
    return policies[app_type]


def refresh_docs_cache() -> str:
    """Refresh cached docs pages and changelogs."""
    cache = DocsCache()
    cache.clear()

    fetched = 0
    errors: list[str] = []

    for path in DOC_PAGES:
        url = f"{DOCS_BASE}{path}"
        try:
            response = httpx.get(url, timeout=15, follow_redirects=True)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            article = soup.find("article") or soup.find(class_="md-content")
            if article is None:
                errors.append(f"{url}: no article content found")
                continue

            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else path
            content = article.get_text(separator="\n", strip=True)
            section = path.strip("/") or "Home"
            cache.store_page(url=url, title=title, content=content, section=section)
            fetched += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")

    try:
        response = httpx.get(GITHUB_API, params={"per_page": 10}, timeout=15)
        response.raise_for_status()
        for release in response.json():
            cache.store_changelog(
                release.get("tag_name", "unknown"),
                release.get("published_at", ""),
                release.get("body", ""),
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"GitHub releases: {exc}")

    report = f"Refreshed docs cache: {fetched} pages fetched."
    if errors:
        report += f"\n\nErrors ({len(errors)}):\n" + "\n".join(f"  - {err}" for err in errors)
    return report
