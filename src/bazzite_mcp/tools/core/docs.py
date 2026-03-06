from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from mcp.server.fastmcp import Context

from bazzite_mcp.config import load_config
from bazzite_mcp.runner import ToolError

_REFERENCE_CONTENT = {
    "install-policy": """
- Prefer `ujust` for Bazzite-native setup and maintenance flows.
- Prefer Flatpak for GUI apps.
- Prefer Homebrew for CLI and TUI tools.
- Prefer Distrobox for development stacks and foreign package ecosystems.
- Treat `rpm-ostree` as a last resort on the host.
- Prefer VMs for untrusted binaries or stronger isolation.
""".strip(),
    "tool-routing": """
- Use MCP for live state, guarded host changes, screenshots, services, packages, containers, VMs, and gaming settings.
- Use local knowledge resources for install policy, troubleshooting, and execution-model guidance.
- Use official docs and source repo pointers for deeper platform reference when the built-in knowledge resources are insufficient.
""".strip(),
    "troubleshooting": """
1. Gather `system_info(detail="basic")`.
2. Use `system_info(detail="full")` when hardware details matter.
3. Run `system_doctor()` for broad checks.
4. Inspect service state with `manage_service(action="status", ...)`.
5. Search built-in knowledge with `docs(action="search", query=...)`.
6. Follow official docs and source repo pointers when deeper Bazzite reference is needed.
""".strip(),
    "dev-environments": """
- Keep the immutable host lean.
- Use Distrobox for most development environments.
- Use the host only for native Bazzite tools and tightly integrated desktop needs.
- Use a VM when you need stronger isolation than a container provides.
""".strip(),
    "game-optimization": """
- Start with Steam, Proton, and MangoHud defaults.
- Use community reports for game-specific compatibility hints.
- Prefer minimally invasive tweaks before layering new host packages.
""".strip(),
}


@dataclass(frozen=True)
class KnowledgeDocument:
    title: str
    summary: str
    body: str
    tags: tuple[str, ...]
    resource_uri: str | None = None
    source_url: str | None = None


def _knowledge_documents() -> list[KnowledgeDocument]:
    cfg = load_config()
    return [
        KnowledgeDocument(
            title="Install Policy",
            summary="Choose the least invasive Bazzite-native install path before layering packages.",
            body=_REFERENCE_CONTENT["install-policy"],
            tags=("install", "packages", "flatpak", "brew", "distrobox", "rpm-ostree"),
            resource_uri="bazzite://knowledge/install-policy",
        ),
        KnowledgeDocument(
            title="Tool Routing",
            summary="Map tasks to MCP tools versus skill reasoning.",
            body=_REFERENCE_CONTENT["tool-routing"],
            tags=("routing", "tools", "workflow", "mcp"),
            resource_uri="bazzite://knowledge/tool-routing",
        ),
        KnowledgeDocument(
            title="Troubleshooting",
            summary="Structured Bazzite troubleshooting flow for system and service issues.",
            body=_REFERENCE_CONTENT["troubleshooting"],
            tags=("troubleshooting", "diagnostics", "services", "desktop"),
            resource_uri="bazzite://knowledge/troubleshooting",
        ),
        KnowledgeDocument(
            title="Dev Environments",
            summary="Guidance for choosing host, Distrobox, or VM for development workloads.",
            body=_REFERENCE_CONTENT["dev-environments"],
            tags=("development", "distrobox", "vm", "containers"),
            resource_uri="bazzite://knowledge/dev-environments",
        ),
        KnowledgeDocument(
            title="Game Optimization",
            summary="Bazzite gaming guidance for Steam, Proton, and performance tuning.",
            body=_REFERENCE_CONTENT["game-optimization"],
            tags=("gaming", "steam", "proton", "performance"),
            resource_uri="bazzite://knowledge/game-optimization",
        ),
        KnowledgeDocument(
            title="Repo Sources",
            summary="Canonical Bazzite GitHub source repo for live code-first reference.",
            body=_repo_sources_body(cfg),
            tags=("github", "repo", "source", "code"),
            resource_uri="bazzite://knowledge/repo-sources",
            source_url=cfg.github_repo_url,
        ),
        KnowledgeDocument(
            title="Official Docs",
            summary="Canonical Bazzite documentation home.",
            body=(
                f"Official Bazzite documentation lives at {cfg.docs_base_url}.\n"
                "Use it for installation, updates, hardware guidance, and general platform docs."
            ),
            tags=("official", "docs", "reference"),
            source_url=cfg.docs_base_url,
        ),
        KnowledgeDocument(
            title="Releases",
            summary="Official Bazzite release history and changelog source.",
            body=(
                f"Official Bazzite release notes live at {cfg.github_releases_url}.\n"
                "Use release pages to inspect what changed between versions."
            ),
            tags=("releases", "changelog", "updates"),
            source_url=cfg.github_releases_url,
        ),
    ]


def _repo_sources_body(cfg) -> str:
    repo = cfg.github_repo_url.rstrip("/")
    return "\n".join(
        [
            f"- Repository root: {repo}",
            "- Use the live GitHub repo for code-first documentation, current file paths, commit history, and search.",
            "- Do not rely on MCP to mirror or index repo structure; browse the upstream repo directly when code details matter.",
            "- Prefer the repo over summaries when you need to confirm how the image is assembled or where a behavior comes from.",
        ]
    )


def _terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"\w+", query)]


def _score_document(doc: KnowledgeDocument, terms: list[str]) -> int:
    haystack = " ".join(
        [
            doc.title,
            doc.summary,
            doc.body,
            " ".join(doc.tags),
            doc.resource_uri or "",
            doc.source_url or "",
        ]
    ).lower()
    return sum(haystack.count(term) for term in terms)


def _snippet(doc: KnowledgeDocument, terms: list[str], max_chars: int = 240) -> str:
    lines = [line.strip() for line in doc.body.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if any(term in lowered for term in terms):
            return line[:max_chars]
    if lines:
        return lines[0][:max_chars]
    return doc.summary[:max_chars]


def knowledge_index_markdown() -> str:
    docs = _knowledge_documents()
    parts = ["# Bazzite Knowledge\n"]

    parts.append("## Local Resources")
    for doc in docs:
        if doc.resource_uri:
            parts.append(f"- `{doc.resource_uri}` — {doc.summary}")

    parts.append("\n## Official Sources")
    for doc in docs:
        if doc.source_url:
            parts.append(f"- {doc.title}: {doc.source_url}")

    return "\n".join(parts)


def knowledge_resource_markdown(slug: str) -> str:
    mapping = {
        "install-policy": "Install Policy",
        "tool-routing": "Tool Routing",
        "troubleshooting": "Troubleshooting",
        "dev-environments": "Dev Environments",
        "game-optimization": "Game Optimization",
        "repo-sources": "Repo Sources",
    }
    title = mapping[slug]
    if slug == "repo-sources":
        return f"# {title}\n\n{_repo_sources_body(load_config())}"
    return f"# {title}\n\n{_REFERENCE_CONTENT[slug]}"


async def _query_bazzite_docs(query: str, ctx: Context | None = None) -> str:
    """Search local Bazzite knowledge and return official doc and repo pointers."""
    terms = _terms(query)
    if not terms:
        return "No searchable terms in query."

    scored = [
        (doc, _score_document(doc, terms))
        for doc in _knowledge_documents()
    ]
    results = [(doc, score) for doc, score in scored if score > 0]
    results.sort(key=lambda item: item[1], reverse=True)

    if ctx:
        await ctx.report_progress(len(results), len(scored))

    if not results:
        return (
            f"No local knowledge results for '{query}'.\n\n"
            f"Official docs: {load_config().docs_base_url}\n"
            f"Official source repo: {load_config().github_repo_url}\n"
            "Use the local knowledge resources for install policy and troubleshooting guidance."
        )

    parts = [f"# Bazzite Knowledge Results for '{query}'\n"]
    for doc, score in results[:5]:
        location = doc.resource_uri or doc.source_url or "local"
        parts.append(
            f"## {doc.title}\n"
            f"{doc.summary}\n\n"
            f"Snippet: {_snippet(doc, terms)}\n"
            f"Location: {location}\n"
            f"Score: {score}"
        )
    return "\n\n".join(parts)


async def _bazzite_changelog(version: str | None = None, count: int = 5) -> str:
    """Return official Bazzite release sources instead of mirroring changelogs locally."""
    cfg = load_config()
    releases_url = cfg.github_releases_url
    if version:
        tag = version.removeprefix("v")
        return (
            f"Official Bazzite release source for '{version}':\n"
            f"{releases_url}/tag/v{tag}\n\n"
            f"All releases: {releases_url}"
        )
    return (
        "Bazzite changelogs are no longer mirrored locally.\n\n"
        f"Official releases: {releases_url}\n"
        f"Requested latest count: {count}"
    )


async def refresh_docs_cache(ctx: Context | None = None) -> str:
    """Compatibility no-op after removing the local docs crawler/cache."""
    if ctx:
        await ctx.report_progress(1, 1)
    return (
        "No-op: local docs crawling and cache refresh were removed. "
        "Use the built-in knowledge resources at bazzite://knowledge/* plus the official Bazzite docs and repo URLs instead."
    )


async def docs(
    action: Literal["search", "changelog", "refresh"],
    query: str | None = None,
    version: str | None = None,
    count: int = 5,
    ctx: Context | None = None,
) -> str:
    """Search local Bazzite knowledge, return official changelog sources, or report docs mode."""
    if action == "search":
        if not query:
            raise ToolError("'query' is required for action='search'.")
        return await _query_bazzite_docs(query, ctx)
    if action == "changelog":
        return await _bazzite_changelog(version, count)
    if action == "refresh":
        return await refresh_docs_cache(ctx)
    raise ToolError(f"Unknown action '{action}'.")
