from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import Context

from bazzite_mcp.config import load_config
from bazzite_mcp.runner import ToolError

_REFERENCES_DIR = Path(__file__).resolve().parents[4] / "skills" / "bazzite-operator" / "references"

_SLUG_TO_FILE = {
    "install-policy": "install-policy.md",
    "tool-routing": "tool-routing.md",
    "troubleshooting": "troubleshooting.md",
    "dev-environments": "dev-environments.md",
    "game-optimization": "game-optimization.md",
}


def _load_reference(slug: str) -> str:
    """Load reference content from the skill reference files (single source of truth)."""
    filename = _SLUG_TO_FILE.get(slug)
    if not filename:
        return ""
    path = _REFERENCES_DIR / filename
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


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
            body=_load_reference("install-policy"),
            tags=("install", "packages", "flatpak", "brew", "distrobox", "rpm-ostree"),
            resource_uri="bazzite://knowledge/install-policy",
        ),
        KnowledgeDocument(
            title="Tool Routing",
            summary="Map tasks to MCP tools versus skill reasoning.",
            body=_load_reference("tool-routing"),
            tags=("routing", "tools", "workflow", "mcp"),
            resource_uri="bazzite://knowledge/tool-routing",
        ),
        KnowledgeDocument(
            title="Troubleshooting",
            summary="Structured Bazzite troubleshooting flow for system and service issues.",
            body=_load_reference("troubleshooting"),
            tags=("troubleshooting", "diagnostics", "services", "desktop"),
            resource_uri="bazzite://knowledge/troubleshooting",
        ),
        KnowledgeDocument(
            title="Dev Environments",
            summary="Guidance for choosing host, Distrobox, or VM for development workloads.",
            body=_load_reference("dev-environments"),
            tags=("development", "distrobox", "vm", "containers"),
            resource_uri="bazzite://knowledge/dev-environments",
        ),
        KnowledgeDocument(
            title="Game Optimization",
            summary="Bazzite gaming guidance for Steam, Proton, and performance tuning.",
            body=_load_reference("game-optimization"),
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
    if slug == "repo-sources":
        return f"# Repo Sources\n\n{_repo_sources_body(load_config())}"
    content = _load_reference(slug)
    if content:
        return content
    return f"No knowledge resource found for '{slug}'."


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


async def docs(
    action: Literal["search", "changelog"],
    query: str | None = None,
    version: str | None = None,
    count: int = 5,
    ctx: Context | None = None,
) -> str:
    """Search local Bazzite knowledge or return official changelog sources."""
    if action == "search":
        if not query:
            raise ToolError("'query' is required for action='search'.")
        return await _query_bazzite_docs(query, ctx)
    if action == "changelog":
        return await _bazzite_changelog(version, count)
    raise ToolError(f"Unknown action '{action}'.")
