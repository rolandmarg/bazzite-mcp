# Bazzite MCP — Improvement Plan

Remaining items from expert review and testing sessions, ordered by priority.
Each item is self-contained with root cause, files to modify, implementation steps,
and verification criteria.

---

## P0: Bug Fixes

### 1. Guardrail false positive on stderr redirects

**Problem:** `ujust_list` runs `ujust --summary 2>/dev/null` which matches the
blocked pattern `>\s*/dev/` — intended to block stdout writes to `/dev/`, not
stderr suppression.

**Root cause:** The regex `r">\s*/dev/"` matches `2>/dev/null` because it doesn't
distinguish between stdout (`>`, `1>`) and stderr (`2>`) redirects.

**Files:** `src/bazzite_mcp/guardrails.py`

**Steps:**
1. Change the `/dev/` blocked pattern from `r">\s*/dev/"` to a negative lookbehind
   that excludes `2>`: `r"(?<![2])>\s*/dev/"` — or use `r"[^2]>\s*/dev/|^>\s*/dev/"`
2. Also ensure `2>/dev/null` specifically is never blocked (it's standard practice)
3. Add test cases to `tests/test_guardrails.py`:
   - `ujust --summary 2>/dev/null` → allowed
   - `echo foo > /dev/sda` → still blocked
   - `cat 2>/dev/null` → allowed

**Verify:** `uv run pytest tests/test_guardrails.py -v`

---

### 2. DB schema migration for `embeddings.model` column

**Problem:** If a user's DB was created before the `model` column was added to the
`embeddings` table, `embed_pages` fails with `no such column: model`.

**Root cause:** `ensure_tables` uses `CREATE TABLE IF NOT EXISTS` which is a no-op
when the table already exists with the old schema. There is no migration system.

**Files:** `src/bazzite_mcp/db.py`

**Steps:**
1. Add a `migrate_cache_schema(conn)` function that runs after `ensure_tables`:
   ```python
   def migrate_cache_schema(conn: Connection) -> None:
       # Check if 'model' column exists in embeddings
       cols = {row[1] for row in conn.execute("PRAGMA table_info(embeddings)").fetchall()}
       if "model" not in cols:
           conn.execute("ALTER TABLE embeddings ADD COLUMN model TEXT DEFAULT ''")
           conn.commit()
   ```
2. Call `migrate_cache_schema` in `DocsCache.__init__` after `ensure_tables`
3. Add a test that creates a DB with old schema, runs migration, verifies column exists

**Verify:** `uv run pytest tests/test_db.py -v`

---

## P1: Search Quality

### 3. Hybrid search (FTS5 + semantic with RRF)

**Problem:** Semantic search returns off-topic results for specific terms (e.g.,
"browser sandbox" returns unrelated pages). Keyword search misses conceptual matches.
Neither alone is sufficient.

**Root cause:** Only one search mode is used per query. No fusion of results.

**Files:**
- `src/bazzite_mcp/tools/docs.py` — new `hybrid_search_docs` tool or merge into existing
- `src/bazzite_mcp/cache/embeddings.py` — expose scored semantic results
- `src/bazzite_mcp/cache/docs_cache.py` — expose scored FTS results

**Steps:**
1. Add a scored FTS search to `DocsCache`:
   ```python
   def search_scored(self, query, limit=20) -> list[tuple[float, dict]]:
       # Return (bm25_rank, result) pairs
   ```
2. Ensure `semantic_search` already returns scores (it does via `score` field)
3. Add Reciprocal Rank Fusion (RRF) function:
   ```python
   def reciprocal_rank_fusion(keyword_results, semantic_results, k=60):
       scores = {}
       for rank, r in enumerate(keyword_results):
           scores[r['url']] = scores.get(r['url'], 0) + 1 / (k + rank + 1)
       for rank, r in enumerate(semantic_results):
           scores[r['url']] = scores.get(r['url'], 0) + 1 / (k + rank + 1)
       # Merge and sort by fused score
   ```
4. Wire into `query_bazzite_docs` or create a new `hybrid_search_docs` tool
5. Add tests with mocked results

**Verify:** `uv run pytest tests/test_tools_docs.py -v`

---

### 4. FTS5 synonym expansion

**Problem:** Keyword search misses obvious synonyms. Searching "browser sandbox"
doesn't find "flatpak permissions" or "flatseal" pages.

**Root cause:** FTS5 tokenization is literal — no synonym mapping.

**Files:**
- `src/bazzite_mcp/cache/docs_cache.py` — query expansion before FTS5 MATCH

**Steps:**
1. Add a synonym dictionary (Bazzite-specific):
   ```python
   SYNONYMS = {
       "browser": ["firefox", "chromium", "brave"],
       "sandbox": ["flatpak", "permissions", "flatseal", "distrobox"],
       "gamepad": ["controller", "joystick", "gamecontroller"],
       "update": ["upgrade", "rebase", "rpm-ostree"],
       ...
   }
   ```
2. Expand the FTS5 query with OR-joined synonyms before matching
3. Keep expansion limited (max 3 synonyms per term) to avoid noise
4. Add tests

**Verify:** `uv run pytest tests/test_docs_cache.py -v`

---

### 5. Better content chunking for embeddings

**Problem:** Current chunking splits on `\n\n` (paragraph boundaries) with a
character limit. This can split mid-section or create chunks that lack context
about what page/topic they belong to.

**Root cause:** `_chunk_text` in `embeddings.py` is purely character-based with
paragraph boundary awareness but no semantic awareness.

**Files:** `src/bazzite_mcp/cache/embeddings.py`

**Steps:**
1. Prepend page title + section to each chunk as context:
   ```python
   prefix = f"[{title} > {section}] "
   ```
2. Split on markdown headers (`## `, `### `) first, then fall back to paragraphs
3. Keep the existing overlap mechanism but apply it after header-based splitting
4. Re-embed all pages after changing chunk strategy (clear embeddings on upgrade)

**Verify:** `uv run pytest tests/test_embeddings.py -v`

---

## P2: Reliability & Robustness

### 6. Make `semantic_search` async end-to-end

**Problem:** `semantic_search` in `embeddings.py` uses synchronous `httpx.post`
for query embedding (`_sync_embed_query`). This blocks the event loop during
search.

**Root cause:** The function was kept sync to avoid requiring `await` at the call
site. But since all tool functions are now async, this can be converted.

**Files:**
- `src/bazzite_mcp/cache/embeddings.py` — convert `semantic_search` and
  `_sync_embed_query` to async
- `src/bazzite_mcp/tools/docs.py` — add `await` to `semantic_search` calls

**Steps:**
1. Rename `_sync_embed_query` → `_embed_query` and make it `async def`
2. Convert `semantic_search` to `async def`
3. Update callers in `docs.py`: `semantic_search_docs` and `query_bazzite_docs`
   fallback path
4. Update tests to use `pytest.mark.asyncio`

**Verify:** `uv run pytest tests/test_embeddings.py tests/test_tools_docs.py -v`

---

### 7. Concurrent page crawling in `refresh_docs_cache`

**Problem:** `refresh_docs_cache` fetches pages one at a time. Crawling 100 pages
sequentially at ~200ms each takes ~20 seconds.

**Root cause:** The crawl loop is `while to_visit: url = to_visit.pop(); await client.get(url)`.

**Files:** `src/bazzite_mcp/tools/docs.py`

**Steps:**
1. Use `asyncio.Semaphore` to limit concurrency (e.g., 5 concurrent fetches)
2. Gather batches of URLs with `asyncio.gather`:
   ```python
   sem = asyncio.Semaphore(5)
   async def fetch_one(url):
       async with sem:
           response = await client.get(url)
           ...
   ```
3. Process discovered links after each batch completes
4. Keep progress reporting accurate (increment after each page, not batch)

**Verify:** Manual test — `uv run python -m bazzite_mcp.refresh` should complete
faster.

---

### 8. Graceful handling of shell metacharacters in guardrails

**Problem:** The guardrails use regex on raw command strings. Commands with shell
metacharacters (`;`, `&&`, `||`, `$()`, backticks) are checked as a single string
but may contain multiple commands.

**Root cause:** `check_command` only extracts and allowlist-checks the *first*
command prefix. A string like `echo hi; rm -rf /` would pass the allowlist check
for `echo` but the blocked patterns would need to catch `rm -rf /`.

**Files:** `src/bazzite_mcp/guardrails.py`

**Steps:**
1. Add shell metacharacter detection as a blocked pattern:
   ```python
   (r"[;&|`]", "shell metacharacters (;, &, |, `) are blocked — use separate commands"),
   (r"\$\(", "command substitution $() is blocked"),
   ```
2. This is stricter than per-command checking but eliminates bypass vectors
3. If legitimate use cases need pipes/chains, add specific allowlist exceptions
4. Update tests in `test_guardrails.py` and `test_security.py`

**Note:** The security tests (`test_security.py`) already test these vectors.
Verify the guardrails actually block them at the pattern level, not just the
allowlist level.

**Verify:** `uv run pytest tests/test_guardrails.py tests/test_security.py -v`

---

## P3: Developer Experience & Operations

### 9. Structured logging

**Problem:** Only `runner.py` uses Python logging. Other modules use no logging,
making it hard to debug issues in production.

**Files:** All files in `src/bazzite_mcp/`

**Steps:**
1. Add `logger = logging.getLogger(__name__)` to each module
2. Log at appropriate levels:
   - `DEBUG`: function entry/exit, cache hits
   - `INFO`: cache refresh start/end, embedding generation
   - `WARNING`: fallback paths taken, stale cache used
   - `ERROR`: API failures, guardrail blocks
3. Configure root logger in `server.py` or `__main__.py`
4. Use structured format: `%(asctime)s %(name)s %(levelname)s %(message)s`

**Verify:** Manual — run the server and check log output.

---

### 10. Config validation

**Problem:** `Config` accepts any values from TOML/env without validation.
Invalid values (negative TTL, empty URLs, unknown provider) cause runtime errors
far from the config loading.

**Files:** `src/bazzite_mcp/config.py`

**Steps:**
1. Add validation in `__post_init__`:
   ```python
   def __post_init__(self):
       if self.cache_ttl_days < 0:
           raise ValueError("cache_ttl_days must be non-negative")
       if self.embedding_provider not in ("gemini", "openai"):
           raise ValueError(f"Unknown embedding_provider: {self.embedding_provider}")
       if self.embedding_dimensions < 1:
           raise ValueError("embedding_dimensions must be positive")
       if self.crawl_max_pages < 1:
           raise ValueError("crawl_max_pages must be positive")
   ```
2. Add tests for invalid configs in `test_config.py`

**Verify:** `uv run pytest tests/test_config.py -v`

---

### 11. Test coverage for edge cases

**Problem:** Several edge cases lack test coverage:
- Empty DB semantic search
- FTS5 query with special characters (already sanitized but untested edge cases)
- Embedding API timeout/error handling
- Config loading with malformed TOML
- `DocsCache.is_stale` with various timestamp formats

**Files:** `tests/test_docs_cache.py`, `tests/test_embeddings.py`, `tests/test_config.py`

**Steps:**
1. Add parametrized tests for `_sanitize_fts5_query` edge cases
2. Add tests for embedding API failures (mock httpx to raise various exceptions)
3. Add tests for `is_stale` with edge timestamps (UTC, naive, Z-suffix, +00:00)
4. Add tests for config with missing/corrupt TOML file

**Verify:** `uv run pytest tests/ -v --tb=short`

---

## P4: Future Enhancements (Lower Priority)

### 12. Reranking with cross-encoder

After hybrid search is in place, add optional cross-encoder reranking for the
top N results. This would use a small model (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`)
to score query-document pairs more accurately than embedding similarity.

This requires adding a Python dependency (`sentence-transformers` or API call)
and is only worth doing after hybrid search proves the fused result set is good.

### 13. Cache warming on server startup

Currently, the cache is only populated when a user queries docs (lazy refresh).
Add optional startup warming via the systemd timer or a background task in `server.py`
so first queries are fast.

### 14. MCP resource subscriptions for cache status

Expose cache freshness as an MCP resource that clients can subscribe to.
When cache becomes stale or refresh completes, notify subscribed clients.

**Files:** `src/bazzite_mcp/resources.py`

### 15. Multi-source documentation

Extend the crawler to support additional doc sources beyond `docs.bazzite.gg`:
- Universal Blue docs
- Fedora Atomic docs
- Relevant Arch Wiki pages

This would require per-source CSS selectors and URL scoping in the config.
