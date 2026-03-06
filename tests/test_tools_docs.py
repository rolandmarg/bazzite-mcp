import asyncio

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.core.docs import _query_bazzite_docs, docs


def test_query_bazzite_docs_returns_local_knowledge() -> None:
    result = asyncio.run(_query_bazzite_docs("rpm-ostree install policy"))
    assert "Install Policy" in result
    assert "bazzite://knowledge/install-policy" in result


def test_query_bazzite_docs_returns_official_source_pointers() -> None:
    result = asyncio.run(_query_bazzite_docs("official docs"))
    assert "Official Docs" in result
    assert "https://docs.bazzite.gg" in result


def test_query_bazzite_docs_returns_repo_source_pointers() -> None:
    result = asyncio.run(_query_bazzite_docs("github source repo"))
    assert "Repo Sources" in result
    assert "https://github.com/ublue-os/bazzite" in result


def test_docs_dispatcher_search_requires_query() -> None:
    with pytest.raises(ToolError, match="query"):
        asyncio.run(docs(action="search"))


def test_docs_dispatcher_changelog_returns_official_release_source() -> None:
    result = asyncio.run(docs(action="changelog", version="41.20240211"))
    assert "Official Bazzite release source" in result
    assert "github.com/ublue-os/bazzite/releases" in result


def test_docs_dispatcher_refresh_is_no_op() -> None:
    result = asyncio.run(docs(action="refresh"))
    assert "No-op" in result
    assert "knowledge resources" in result


def test_docs_dispatcher_rejects_removed_policy_action() -> None:
    with pytest.raises(ToolError, match="Unknown action"):
        asyncio.run(docs(action="policy"))  # type: ignore[arg-type]
