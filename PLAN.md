# Bazzite MCP — Improvement Plan

Remaining items from expert review and testing sessions, ordered by priority.
Each item is self-contained with root cause, files to modify, implementation steps,
and verification criteria.

---

## Completed

### ~~1. Guardrail false positive on stderr redirects~~ DONE

Fixed: `/dev/` blocked pattern now uses `(?<![0-9])>>?\s*/dev/` to exclude
`2>/dev/null` while still blocking `> /dev/sda`.

### ~~4. FTS5 synonym expansion~~ DONE

Implemented in `src/bazzite_mcp/cache/docs_cache.py` with `SYNONYMS` dict
and `_expand_fts5_query()`. Terms are OR-expanded before FTS5 MATCH.

### ~~8. Shell metacharacter guardrails~~ DONE

Implemented: `[;|`]|&&|\|\|` and `\$\(` patterns block all shell chaining
and command substitution.

### ~~9. Structured logging~~ PARTIALLY DONE

`logging.getLogger(__name__)` added to `config.py`, `docs_cache.py`, `gaming.py`.
Remaining modules still lack logging.

### ~~10. Config validation~~ DONE

`Config.validate()` in `config.py` checks `cache_ttl_days`, `cache_ttl_hours`,
and `crawl_max_pages`. Called from `__post_init__`.

---

## Obsolete (removed features)

The following items depended on the embedding/semantic search system which was
removed in commit `254552a` (refactor: drop self-improve tools and embedding system):

- ~~2. DB schema migration for `embeddings.model` column~~
- ~~3. Hybrid search (FTS5 + semantic with RRF)~~
- ~~5. Better content chunking for embeddings~~
- ~~6. Make `semantic_search` async end-to-end~~
- ~~12. Reranking with cross-encoder~~

---

## P1: Reliability & Performance

### 7. Concurrent page crawling in `refresh_docs_cache`

**Problem:** `refresh_docs_cache` fetches pages one at a time. Crawling 100 pages
sequentially at ~200ms each takes ~20 seconds.

**Root cause:** The crawl loop is `while to_visit: url = to_visit.pop(); await client.get(url)`.

**Files:** `src/bazzite_mcp/tools/docs.py`

**Steps:**
1. Use `asyncio.Semaphore` to limit concurrency (e.g., 5 concurrent fetches)
2. Gather batches of URLs with `asyncio.gather`
3. Process discovered links after each batch completes
4. Keep progress reporting accurate (increment after each page, not batch)

**Verify:** Manual test — `uv run python -m bazzite_mcp.refresh` should complete
faster.

---

## P2: Developer Experience

### 11. Test coverage for edge cases

**Problem:** Several edge cases lack test coverage:
- FTS5 query with special characters (already sanitized but untested edge cases)
- Config loading with malformed TOML
- `DocsCache.is_stale` with various timestamp formats

**Files:** `tests/test_docs_cache.py`, `tests/test_config.py`

**Steps:**
1. Add parametrized tests for `_sanitize_fts5_query` edge cases
2. Add tests for `is_stale` with edge timestamps (UTC, naive, Z-suffix, +00:00)
3. Add tests for config with missing/corrupt TOML file

**Verify:** `uv run pytest tests/ -v --tb=short`

---

## P3: Code Gaps

### 16. Implement `manage_waydroid` tool

**Problem:** `manage_waydroid` is documented in README and design docs, listed in
the guardrails allowlist (`waydroid` command), but was never implemented.

**Files:**
- `src/bazzite_mcp/tools/containers.py` — add `manage_waydroid` function
- `src/bazzite_mcp/server.py` — register the tool
- `tests/test_tools_containers.py` — add tests

**Steps:**
1. Add `manage_waydroid(action)` with actions: `setup`, `status`, `start`, `stop`
2. `setup` should delegate to `ujust setup-waydroid`
3. `start`/`stop` should use `waydroid session start/stop`
4. `status` should use `waydroid status`
5. Register in `server.py`

**Verify:** `uv run pytest tests/test_tools_containers.py -v`

---

### 17. Complete structured logging

**Problem:** Only `config.py`, `docs_cache.py`, and `gaming.py` have
`logger = logging.getLogger(__name__)`. Other modules lack logging, making
production debugging harder.

**Files:** All files in `src/bazzite_mcp/` without a logger

**Steps:**
1. Add `logger = logging.getLogger(__name__)` to each module
2. Log at appropriate levels (DEBUG for cache hits, INFO for refresh, WARNING for
   fallbacks, ERROR for guardrail blocks)

**Verify:** Manual — run the server and check log output.

---

## P4: Future Enhancements (Lower Priority)

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
