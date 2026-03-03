"""Cloud-based embedding generation + local vector search.

Embeddings are generated via an OpenAI-compatible API during cache refresh,
then stored as raw float32 blobs in SQLite for offline semantic search.
"""

import os
import struct
from sqlite3 import Connection

import httpx

from bazzite_mcp.config import load_config


def _get_api_key() -> str | None:
    cfg = load_config()
    return os.environ.get(cfg.embedding_api_key_env)


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > chunk_size and current:
            chunks.append(current.strip())
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


def generate_embeddings(texts: list[str]) -> list[list[float]] | None:
    """Call the embedding API for a batch of texts. Returns None if unavailable."""
    api_key = _get_api_key()
    if not api_key:
        return None

    cfg = load_config()
    try:
        response = httpx.post(
            cfg.embedding_api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "input": texts,
                "model": cfg.embedding_model,
                "dimensions": cfg.embedding_dimensions,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        # OpenAI-compatible response: {"data": [{"embedding": [...], "index": 0}, ...]}
        results = sorted(data["data"], key=lambda x: x["index"])
        return [r["embedding"] for r in results]
    except Exception:
        return None


def embed_pages(conn: Connection) -> tuple[int, list[str]]:
    """Generate embeddings for all pages that don't have them yet.

    Returns (count_embedded, errors).
    """
    cfg = load_config()
    api_key = _get_api_key()
    if not api_key:
        return 0, [f"No API key found in ${cfg.embedding_api_key_env}. Set it to enable semantic search."]

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

    # Process in batches of 20 (API limit friendly)
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
        vectors = generate_embeddings(texts)

        if vectors is None:
            errors.append(f"Embedding API call failed for batch starting at page {batch[0]['id']}")
            continue

        for (page_id, chunk_idx, chunk_text), vec in zip(all_chunks, vectors):
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (page_id, chunk_index, chunk_text, embedding, dimensions) "
                "VALUES (?, ?, ?, ?, ?)",
                (page_id, chunk_idx, chunk_text, _encode_vector(vec), len(vec)),
            )
            embedded += 1

        conn.commit()

    return embedded, errors


def semantic_search(conn: Connection, query: str, limit: int = 5) -> list[dict]:
    """Search cached docs by semantic similarity.

    Embeds the query via API, then ranks stored chunks by cosine similarity.
    """
    query_vecs = generate_embeddings([query])
    if query_vecs is None:
        return []

    query_vec = query_vecs[0]
    cfg = load_config()

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
        scored.append((sim, {
            "title": row["title"],
            "section": row["section"],
            "url": row["url"],
            "content": row["chunk_text"],
            "score": round(sim, 4),
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]
