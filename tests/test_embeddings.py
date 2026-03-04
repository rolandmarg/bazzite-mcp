import asyncio
import httpx
from unittest.mock import AsyncMock, patch

from bazzite_mcp.cache.embeddings import (
    _chunk_text,
    _cosine_similarity,
    _decode_vector,
    _embed_query,
    _encode_vector,
    semantic_search,
)
from bazzite_mcp.db import ensure_tables, get_connection, get_db_path


def test_encode_decode_roundtrip():
    vec = [0.1, 0.2, 0.3, 0.4, 0.5]
    blob = _encode_vector(vec)
    decoded = _decode_vector(blob, len(vec))
    for a, b in zip(vec, decoded):
        assert abs(a - b) < 1e-6


def test_cosine_similarity_identical():
    vec = [1.0, 0.0, 0.0]
    assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert abs(_cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_opposite():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6


def test_chunk_text_splits_at_paragraphs():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = _chunk_text(text, chunk_size=40)
    assert len(chunks) >= 2
    assert "First paragraph." in chunks[0]


def test_chunk_text_single_chunk():
    text = "Short text."
    chunks = _chunk_text(text, chunk_size=2000)
    assert len(chunks) == 1
    assert chunks[0] == "Short text."


def test_chunk_text_splits_on_markdown_headers():
    text = "## One\n\n" + ("a " * 80) + "\n\n## Two\n\n" + ("b " * 80)
    chunks = _chunk_text(text, chunk_size=120)
    assert len(chunks) >= 2
    assert any("## One" in chunk for chunk in chunks)
    assert any("## Two" in chunk for chunk in chunks)


def test_chunk_text_prefixes_context_when_provided():
    chunks = _chunk_text(
        "Content paragraph.",
        chunk_size=200,
        title="Install Guide",
        section="General",
    )
    assert chunks[0].startswith("[Install Guide > General] ")


def test_semantic_search_returns_empty_when_embeddings_table_empty(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    conn = get_connection(get_db_path("cache-empty-search.db"))
    ensure_tables(conn, "cache")

    with patch(
        "bazzite_mcp.cache.embeddings._embed_query",
        new=AsyncMock(return_value=[0.1, 0.2, 0.3]),
    ):
        results = asyncio.run(semantic_search(conn, "test query", limit=5))
    conn.close()
    assert results == []


def test_embed_query_handles_timeout_for_gemini():
    class DummyCfg:
        embedding_provider = "gemini"
        embedding_model = "gemini-embedding-001"
        embedding_dimensions = 768

    with patch(
        "bazzite_mcp.cache.embeddings.httpx.AsyncClient.post",
        new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
    ):
        result = asyncio.run(_embed_query("hello", "fake-key", DummyCfg()))
    assert result is None
