"""Cloud-based embedding generation + local vector search.

Supports Gemini (free) and OpenAI embedding APIs.
Embeddings are generated during cache refresh, then stored as raw float32
blobs in SQLite for offline semantic search.
"""

from __future__ import annotations

import os
import struct
from sqlite3 import Connection

import httpx

from bazzite_mcp.config import load_config

# Minimum cosine similarity to include in search results
MIN_SIMILARITY_THRESHOLD = 0.3

# Overlap between chunks (in characters) to preserve context at boundaries
CHUNK_OVERLAP = 200


def _get_api_key() -> str | None:
    cfg = load_config()
    return os.environ.get(cfg.embedding_api_key_env)


def _current_model_id() -> str:
    """Return a string identifying the current embedding provider+model."""
    cfg = load_config()
    return f"{cfg.embedding_provider}/{cfg.embedding_model}"


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    """Split text into chunks at paragraph boundaries with overlap."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > chunk_size and current:
            chunks.append(current.strip())
            # Keep overlap from the end of previous chunk
            if CHUNK_OVERLAP > 0 and len(current) > CHUNK_OVERLAP:
                current = current[-CHUNK_OVERLAP:] + "\n\n" + para
            else:
                current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text[:chunk_size]]


def _encode_vector(vec: list[float]) -> bytes:
    """Encode a float vector to bytes for SQLite storage."""
    return struct.pack(f"{len(vec)}f", *vec)


def _decode_vector(blob: bytes, dimensions: int) -> list[float]:
    """Decode bytes from SQLite back to a float vector."""
    return list(struct.unpack(f"{dimensions}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _embed_gemini(texts: list[str], api_key: str) -> list[list[float]] | None:
    """Generate embeddings via Google Gemini REST API (free tier)."""
    cfg = load_config()
    model = cfg.embedding_model
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    # Use batchEmbedContents for efficiency
    requests = []
    for text in texts:
        requests.append({
            "model": f"models/{model}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": cfg.embedding_dimensions,
            "taskType": "RETRIEVAL_DOCUMENT",
        })

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{base_url}/models/{model}:batchEmbedContents",
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json={"requests": requests},
            )
            response.raise_for_status()
            data = response.json()
            return [emb["values"] for emb in data["embeddings"]]
    except Exception:
        return None


async def _embed_gemini_query(texts: list[str], api_key: str) -> list[list[float]] | None:
    """Generate query embeddings via Gemini (uses RETRIEVAL_QUERY task type)."""
    cfg = load_config()
    model = cfg.embedding_model
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    requests = []
    for text in texts:
        requests.append({
            "model": f"models/{model}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": cfg.embedding_dimensions,
            "taskType": "RETRIEVAL_QUERY",
        })

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{base_url}/models/{model}:batchEmbedContents",
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json={"requests": requests},
            )
            response.raise_for_status()
            data = response.json()
            return [emb["values"] for emb in data["embeddings"]]
    except Exception:
        return None


async def _embed_openai(texts: list[str], api_key: str) -> list[list[float]] | None:
    """Generate embeddings via OpenAI-compatible API."""
    cfg = load_config()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "input": texts,
                    "model": cfg.embedding_model,
                    "dimensions": cfg.embedding_dimensions,
                },
            )
            response.raise_for_status()
            data = response.json()
            results = sorted(data["data"], key=lambda x: x["index"])
            return [r["embedding"] for r in results]
    except Exception:
        return None


async def generate_embeddings(texts: list[str], query: bool = False) -> list[list[float]] | None:
    """Call the configured embedding API. Returns None if unavailable.

    Args:
        texts: List of texts to embed.
        query: If True, use query-optimized task type (Gemini only).
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    cfg = load_config()
    if cfg.embedding_provider == "gemini":
        if query:
            return await _embed_gemini_query(texts, api_key)
        return await _embed_gemini(texts, api_key)
    return await _embed_openai(texts, api_key)


async def embed_pages(conn: Connection) -> tuple[int, list[str]]:
    """Generate embeddings for all pages that don't have them yet.

    Invalidates embeddings from a different model before re-embedding.
    Returns (count_embedded, errors).
    """
    cfg = load_config()
    api_key = _get_api_key()
    if not api_key:
        return 0, [f"No API key found in ${cfg.embedding_api_key_env}. Set it to enable semantic search."]

    model_id = _current_model_id()

    # Invalidate embeddings from a different model
    stale = conn.execute(
        "SELECT COUNT(*) AS cnt FROM embeddings WHERE model != ? AND model != ''",
        (model_id,),
    ).fetchone()
    if stale and stale["cnt"] > 0:
        conn.execute("DELETE FROM embeddings WHERE model != ?", (model_id,))
        conn.commit()

    # Find pages without embeddings
    rows = conn.execute(
        "SELECT p.id, p.title, p.content FROM pages p "
        "LEFT JOIN embeddings e ON p.id = e.page_id "
        "WHERE e.id IS NULL"
    ).fetchall()

    if not rows:
        return 0, []

    errors: list[str] = []
    embedded = 0

    # Process in batches (Gemini batch limit is 100)
    batch_size = 20
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        all_chunks: list[tuple[int, int, str]] = []  # (page_id, chunk_index, text)

        for row in batch:
            page_id = row["id"]
            title = row["title"] or ""
            content = row["content"] or ""
            full_text = f"{title}\n\n{content}"
            chunks = _chunk_text(full_text, cfg.embedding_chunk_size)
            for idx, chunk in enumerate(chunks):
                all_chunks.append((page_id, idx, chunk))

        texts = [chunk[2] for chunk in all_chunks]
        vectors = await generate_embeddings(texts)

        if vectors is None:
            errors.append(f"Embedding API call failed for batch starting at page {batch[0]['id']}")
            continue

        for (page_id, chunk_idx, chunk_text), vec in zip(all_chunks, vectors):
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (page_id, chunk_index, chunk_text, embedding, dimensions, model) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (page_id, chunk_idx, chunk_text, _encode_vector(vec), len(vec), model_id),
            )
            embedded += 1

        conn.commit()

    return embedded, errors


def semantic_search(conn: Connection, query: str, limit: int = 5) -> list[dict]:
    """Search cached docs by semantic similarity.

    Embeds the query via API, then ranks stored chunks by cosine similarity.
    Filters out results below MIN_SIMILARITY_THRESHOLD.

    Note: This remains synchronous because it's called from tools that need
    immediate results and the query embedding is a single fast API call.
    For the query path, we use synchronous httpx to avoid requiring await.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    cfg = load_config()
    query_vec = _sync_embed_query(query, api_key, cfg)
    if query_vec is None:
        return []

    rows = conn.execute(
        "SELECT e.chunk_text, e.embedding, e.dimensions, p.url, p.title, p.section "
        "FROM embeddings e JOIN pages p ON e.page_id = p.id"
    ).fetchall()

    if not rows:
        return []

    scored: list[tuple[float, dict]] = []
    for row in rows:
        stored_vec = _decode_vector(row["embedding"], row["dimensions"])
        sim = _cosine_similarity(query_vec, stored_vec)
        if sim < MIN_SIMILARITY_THRESHOLD:
            continue
        scored.append((sim, {
            "title": row["title"],
            "section": row["section"],
            "url": row["url"],
            "content": row["chunk_text"],
            "score": round(sim, 4),
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def _sync_embed_query(query: str, api_key: str, cfg) -> list[float] | None:
    """Synchronous single-query embedding for search-time use."""
    if cfg.embedding_provider == "gemini":
        model = cfg.embedding_model
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        try:
            response = httpx.post(
                f"{base_url}/models/{model}:batchEmbedContents",
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json={"requests": [{
                    "model": f"models/{model}",
                    "content": {"parts": [{"text": query}]},
                    "outputDimensionality": cfg.embedding_dimensions,
                    "taskType": "RETRIEVAL_QUERY",
                }]},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data["embeddings"][0]["values"]
        except Exception:
            return None
    else:
        try:
            response = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "input": [query],
                    "model": cfg.embedding_model,
                    "dimensions": cfg.embedding_dimensions,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception:
            return None
