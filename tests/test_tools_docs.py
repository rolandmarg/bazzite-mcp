import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bs4 import BeautifulSoup

from bazzite_mcp.tools.docs import (
    _discover_doc_links,
    _extract_content,
    install_policy,
    query_bazzite_docs,
    semantic_search_docs,
)


def test_install_policy_gui_app() -> None:
    result = install_policy("gui")
    assert "flatpak" in result.lower()


def test_install_policy_cli_tool() -> None:
    result = install_policy("cli")
    assert "brew" in result.lower() or "homebrew" in result.lower()


# --- _extract_content tests ---


def _make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_extract_content_article_selector() -> None:
    html = "<html><body><article>A" + " word" * 20 + "</article></body></html>"
    result = _extract_content(_make_soup(html))
    assert result is not None
    assert "word" in result


def test_extract_content_md_content_class() -> None:
    html = (
        '<html><body><div class="md-content">B' + " text" * 20 + "</div></body></html>"
    )
    result = _extract_content(_make_soup(html))
    assert result is not None
    assert "text" in result


def test_extract_content_md_content_inner_class() -> None:
    html = (
        '<html><body><div class="md-content__inner">C'
        + " data" * 20
        + "</div></body></html>"
    )
    result = _extract_content(_make_soup(html))
    assert result is not None
    assert "data" in result


def test_extract_content_main_tag() -> None:
    html = "<html><body><main>D" + " main" * 20 + "</main></body></html>"
    result = _extract_content(_make_soup(html))
    assert result is not None
    assert "main" in result


def test_extract_content_role_main() -> None:
    html = '<html><body><div role="main">E' + " role" * 20 + "</div></body></html>"
    result = _extract_content(_make_soup(html))
    assert result is not None
    assert "role" in result


def test_extract_content_id_content() -> None:
    html = '<html><body><div id="content">F' + " content" * 20 + "</div></body></html>"
    result = _extract_content(_make_soup(html))
    assert result is not None
    assert "content" in result


def test_extract_content_body_fallback() -> None:
    # No selectors match, but body has enough text (after removing nav/header/footer)
    html = "<html><body><div>G" + " fallback" * 20 + "</div></body></html>"
    result = _extract_content(_make_soup(html))
    assert result is not None
    assert "fallback" in result


def test_extract_content_returns_none_when_too_short() -> None:
    html = "<html><body><div>Hi</div></body></html>"
    result = _extract_content(_make_soup(html))
    assert result is None


def test_extract_content_strips_nav_header_footer_in_body_fallback() -> None:
    html = (
        "<html><body>"
        "<nav>Navigation stuff that is long enough to matter for testing</nav>"
        "<header>Header that is long enough</header>"
        "<div>Z" + " body" * 20 + "</div>"
        "<footer>Footer content</footer>"
        "</body></html>"
    )
    result = _extract_content(_make_soup(html))
    assert result is not None
    assert "Navigation" not in result
    assert "Footer" not in result
    assert "body" in result


# --- _discover_doc_links tests ---


@patch("bazzite_mcp.tools.docs.load_config")
def test_discover_doc_links_internal_links(mock_cfg: MagicMock) -> None:
    cfg = MagicMock()
    cfg.docs_base_url = "https://docs.bazzite.gg"
    mock_cfg.return_value = cfg

    html = """
    <html><body>
        <a href="/General/Installation_Guide/">Install Guide</a>
        <a href="/Advanced/Reset/">Reset</a>
    </body></html>
    """
    soup = _make_soup(html)
    links = _discover_doc_links(soup, "https://docs.bazzite.gg/")
    assert "https://docs.bazzite.gg/General/Installation_Guide/" in links
    assert "https://docs.bazzite.gg/Advanced/Reset/" in links


@patch("bazzite_mcp.tools.docs.load_config")
def test_discover_doc_links_filters_external(mock_cfg: MagicMock) -> None:
    cfg = MagicMock()
    cfg.docs_base_url = "https://docs.bazzite.gg"
    mock_cfg.return_value = cfg

    html = """
    <html><body>
        <a href="https://github.com/ublue-os/bazzite">GitHub</a>
        <a href="https://external.example.com/page">External</a>
    </body></html>
    """
    soup = _make_soup(html)
    links = _discover_doc_links(soup, "https://docs.bazzite.gg/")
    assert len(links) == 0


@patch("bazzite_mcp.tools.docs.load_config")
def test_discover_doc_links_filters_anchors(mock_cfg: MagicMock) -> None:
    cfg = MagicMock()
    cfg.docs_base_url = "https://docs.bazzite.gg"
    mock_cfg.return_value = cfg

    html = """
    <html><body>
        <a href="#section-one">Anchor Link</a>
        <a href="/General/FAQ/#some-section">FAQ Anchor</a>
    </body></html>
    """
    soup = _make_soup(html)
    links = _discover_doc_links(soup, "https://docs.bazzite.gg/")
    # Pure anchor should produce no link; FAQ anchor has a fragment so should be filtered
    for link in links:
        assert "#" not in link


@patch("bazzite_mcp.tools.docs.load_config")
def test_discover_doc_links_filters_cdn_cgi(mock_cfg: MagicMock) -> None:
    cfg = MagicMock()
    cfg.docs_base_url = "https://docs.bazzite.gg"
    mock_cfg.return_value = cfg

    html = """
    <html><body>
        <a href="/cdn-cgi/l/email-protection">CDN Link</a>
    </body></html>
    """
    soup = _make_soup(html)
    links = _discover_doc_links(soup, "https://docs.bazzite.gg/")
    assert len(links) == 0


# --- query_bazzite_docs tests (async) ---


@patch("bazzite_mcp.tools.docs.refresh_docs_cache", new_callable=AsyncMock)
@patch("bazzite_mcp.tools.docs.DocsCache")
def test_query_bazzite_docs_auto_refreshes_when_empty(
    mock_cache_cls: MagicMock,
    mock_refresh: AsyncMock,
) -> None:
    empty_cache = MagicMock()
    empty_cache.page_count.return_value = 0

    refreshed_cache = MagicMock()
    refreshed_cache.page_count.return_value = 1
    refreshed_cache.search.return_value = [
        {
            "title": "Installation Guide",
            "section": "General",
            "content": "Install steps" + " x" * 50,
            "url": "https://docs.bazzite.gg/General/Installation_Guide/",
        }
    ]

    mock_cache_cls.side_effect = [empty_cache, refreshed_cache]
    mock_refresh.return_value = "Refreshed docs cache: 1 pages crawled (max 100)."

    result = asyncio.run(query_bazzite_docs("installation"))
    assert "Installation Guide" in result
    assert "auto-refreshed docs cache" in result
    mock_refresh.assert_called_once()


@patch("bazzite_mcp.tools.docs.DocsCache")
def test_query_bazzite_docs_with_results(mock_cache_cls: MagicMock) -> None:
    mock_cache = MagicMock()
    mock_cache.page_count.return_value = 50
    mock_cache.search.return_value = [
        {
            "title": "Installation Guide",
            "section": "General",
            "content": "Follow these steps to install Bazzite on your system."
            + " x" * 200,
            "url": "https://docs.bazzite.gg/General/Installation_Guide/",
        }
    ]
    mock_cache.is_stale.return_value = False
    mock_cache_cls.return_value = mock_cache

    result = asyncio.run(query_bazzite_docs("installation"))
    assert "Installation Guide" in result
    assert "General" in result
    assert "Source:" in result


@patch("bazzite_mcp.tools.docs.DocsCache")
def test_query_bazzite_docs_no_results(mock_cache_cls: MagicMock) -> None:
    mock_cache = MagicMock()
    mock_cache.page_count.return_value = 50
    mock_cache.is_stale.return_value = False
    mock_cache.search.return_value = []
    mock_cache_cls.return_value = mock_cache

    result = asyncio.run(query_bazzite_docs("xyznonexistent"))
    assert "No results" in result
    assert "xyznonexistent" in result


@patch("bazzite_mcp.tools.docs.semantic_search")
@patch("bazzite_mcp.tools.docs.refresh_docs_cache", new_callable=AsyncMock)
@patch("bazzite_mcp.tools.docs.DocsCache")
def test_semantic_search_auto_refreshes_when_empty(
    mock_cache_cls: MagicMock,
    mock_refresh: AsyncMock,
    mock_semantic_search: MagicMock,
) -> None:
    empty_cache = MagicMock()
    empty_cache.page_count.return_value = 0

    refreshed_cache = MagicMock()
    refreshed_cache.page_count.return_value = 10
    refreshed_cache._conn = MagicMock()

    mock_cache_cls.side_effect = [empty_cache, refreshed_cache]
    mock_refresh.return_value = "Refreshed docs cache: 10 pages crawled (max 100)."
    mock_semantic_search.return_value = [
        {
            "title": "Waydroid Setup",
            "section": "android",
            "url": "https://docs.bazzite.gg/Installing_and_Managing_Software/Waydroid/",
            "content": "Use Waydroid to run Android apps.",
            "score": 0.9231,
        }
    ]

    result = asyncio.run(semantic_search_docs("how to run android apps", limit=3))
    assert "Waydroid Setup" in result
    assert "score" in result
    assert "auto-refreshed docs cache" in result
    mock_refresh.assert_called_once()
