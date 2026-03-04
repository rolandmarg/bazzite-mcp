# Architecture

MCP server giving AI agents awareness and control of a Bazzite OS installation.
Runs on the host over stdio via FastMCP.

```
MCP Client ──stdio──▶ FastMCP (server.py)
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
           tools/      resources   prompts
              │
              ▼
          runner.py ──▶ guardrails.py ──▶ subprocess.run()
              │
              ▼
          audit.py ──▶ audit_log.db

          docs.py  ──▶ httpx ──▶ docs.bazzite.gg / Gemini API
              │
              ▼
          docs_cache.db (FTS5 + vector embeddings)
```

## Why it runs on the host

bazzite-mcp needs direct access to host commands (`systemctl`, `rpm-ostree`,
`ujust`, `firewall-cmd`). Containerizing it would require enough holes to negate
the isolation. Security is handled by the guardrails layer instead.

## Command pipeline

Every shell command flows through the same path. No tool calls `subprocess` directly.

1. **Guardrails** — blocked pattern regex + command allowlist. Raises `GuardrailError` before execution.
2. **subprocess.run** — `shell=True`, `stdin=DEVNULL`, `start_new_session=True`, `timeout=120`
3. **Audit** — mutating commands logged to SQLite with rollback commands

## Layout

```
src/bazzite_mcp/
├── server.py            # FastMCP instance, registers tools/resources/prompts
├── runner.py            # run_command(), run_audited()
├── guardrails.py        # Allowlist + blocked patterns
├── audit.py             # SQLite audit trail
├── db.py                # SQLite helpers and schemas
├── config.py            # Defaults < config.toml < env vars
├── cache/
│   ├── docs_cache.py    # FTS5 keyword search
│   └── embeddings.py    # Vector embeddings + cosine similarity
└── tools/
    ├── ujust.py         # ujust (Tier 1)
    ├── packages.py      # flatpak/brew/rpm-ostree
    ├── services.py      # systemd, networking, firewall
    ├── containers.py    # distrobox, podman, quadlet, waydroid
    ├── system.py        # Read-only introspection
    ├── settings.py      # GNOME/desktop settings
    ├── docs.py          # Docs search + crawler
    ├── audit_tools.py   # Audit log query + rollback
    └── self_improve.py  # GitHub issue/PR loop
```

## Storage

Two SQLite databases in `~/.local/share/bazzite-mcp/`:

- **audit_log.db** — every mutating command with timestamp, args, output, and rollback command
- **docs_cache.db** — crawled pages (FTS5-indexed), vector embeddings (float32 blobs), changelogs

## Config

```
Dataclass defaults  <  ~/.config/bazzite-mcp/config.toml  <  env vars
```

## Dependencies

```
fastmcp, httpx, beautifulsoup4
```

No LLM SDK. Embeddings via raw HTTP to Gemini/OpenAI. Python 3.11+.
