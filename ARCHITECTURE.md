# Architecture

MCP server giving AI agents awareness and control of a Bazzite OS installation.
Runs on the host over stdio via FastMCP.

Install/upgrade/uninstall is handled with `uv tool`:

- Install: `uv tool install bazzite-mcp`
- Upgrade: `uv tool upgrade bazzite-mcp`
- Uninstall: `uv tool uninstall bazzite-mcp`

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

          docs.py  ──▶ httpx ──▶ docs.bazzite.gg / GitHub API
              │
              ▼
          docs_cache.db (FTS5 with synonym expansion)
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
├── server.py            # FastMCP instance, registers 24 tools/resources/prompts
├── runner.py            # run_command(), run_audited()
├── guardrails.py        # Allowlist + blocked patterns
├── audit.py             # SQLite audit trail
├── db.py                # SQLite helpers and schemas
├── config.py            # Defaults < config.toml < env vars
├── cleanup.py           # Data cleanup and uninstall utilities
├── refresh.py           # Standalone docs refresh entrypoint
├── cache/
│   └── docs_cache.py    # FTS5 keyword search with synonym expansion
└── tools/
    ├── ujust.py         # ujust (Tier 1)
    ├── packages.py      # flatpak/brew/rpm-ostree
    ├── services.py      # systemd, networking, firewall, tailscale
    ├── containers.py    # distrobox, podman, quadlet
    ├── system.py        # System info, storage, health checks, snapshots
    ├── settings.py      # Desktop settings (theme, audio, display, power)
    ├── desktop.py       # Screenshots, window management, AT-SPI, input
    ├── virtualization.py # libvirt/KVM setup, VM lifecycle, snapshots
    ├── gaming.py        # Steam library, ProtonDB reports, MangoHud
    ├── docs.py          # Docs search + crawler + changelog
    └── audit_tools.py   # Audit log query + rollback
```

## Console scripts

The package publishes three console commands:

- `bazzite-mcp` — starts the MCP server (`stdio` transport)
- `bazzite-mcp-refresh` — refreshes docs cache
- `bazzite-mcp-cleanup` — removes local cache/audit/config data

## Storage

Two SQLite databases in `~/.local/share/bazzite-mcp/`:

- **audit_log.db** — every mutating command with timestamp, args, output, and rollback command
- **docs_cache.db** — crawled pages (FTS5-indexed), changelogs, game report cache

## Config

```
Dataclass defaults  <  ~/.config/bazzite-mcp/config.toml  <  env vars
```

## Dependencies

```
fastmcp, httpx, beautifulsoup4, vdf
```

Python 3.11+.
