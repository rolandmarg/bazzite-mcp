# Architecture

Repository for Bazzite host capabilities plus companion skill content.
The MCP server runs on the host over stdio via FastMCP.

Install/upgrade/uninstall is handled with `uv tool`:

- Install: `uv tool install bazzite-mcp`
- Upgrade: `uv tool upgrade bazzite-mcp`
- Uninstall: `uv tool uninstall bazzite-mcp`

```
MCP Client ──stdio──▶ FastMCP (server.py)
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
           tools/      resources   audit
              │
              ▼
          runner.py ──▶ guardrails.py ──▶ subprocess.run()
              │
              ▼
          audit.py ──▶ audit_log.db
```

## Boundary

The repo is split into two layers:

- `src/bazzite_mcp/` is the capability layer. It owns host access, tool registration, guardrails, audit logging, built-in knowledge resources, and live state.
- `skills/bazzite-operator/` is the workflow layer. It owns install-policy guidance, troubleshooting sequences, and task-to-tool routing heuristics.

Keep runtime behavior in MCP. Keep reusable reasoning and platform policy in the skill. Static policy and workflow prompts are intentionally absent from MCP.

## Why it runs on the host

bazzite-mcp needs direct access to host commands (`systemctl`, `rpm-ostree`,
`ujust`, `firewall-cmd`). Containerizing it would require enough holes to negate
the isolation. Security is handled by the guardrails layer instead.

## Command pipeline

Every host command flows through the same path. Most tools do not call `subprocess` directly.

1. **Guardrails** — command allowlist + safety checks. Raises `GuardrailError` before execution.
2. **subprocess.run** — `shell=False`, `stdin=DEVNULL`, `start_new_session=True`, `timeout=120`
3. **Audit** — mutating commands logged to SQLite with rollback commands

## Layout

```
src/bazzite_mcp/
├── server.py            # FastMCP instance, registers tools and dynamic resources
├── runner.py            # run_command(), run_audited()
├── guardrails.py        # Allowlist + blocked patterns
├── audit.py             # SQLite audit trail
├── db.py                # SQLite helpers and schemas
├── config.py            # Defaults < config.toml < env vars
├── cleanup.py           # Data cleanup and uninstall utilities
└── tools/
    ├── core/
    │   ├── __init__.py  # public core tool exports and compatibility surface
    │   ├── ujust.py     # ujust (Tier 1)
    │   ├── packages.py  # flatpak/brew/rpm-ostree
    │   ├── docs.py      # Local knowledge lookup + official source pointers
    │   └── audit.py     # Audit log query + rollback
    ├── settings/
    │   ├── __init__.py  # public desktop setting exports
    │   ├── quick.py     # theme, audio, and power profile helpers
    │   ├── display.py   # display query and display config changes
    │   └── schema.py    # raw gsettings read/write access
    ├── desktop/
    │   ├── __init__.py      # public desktop tool exports
    │   ├── accessibility.py # AT-SPI inspection and element actions
    │   ├── windows.py       # KWin window lookup, activation, inspection
    │   ├── capture.py       # screenshots and portal session setup
    │   ├── input.py         # ydotool keyboard and mouse input
    │   └── shared.py        # shared portal and screenshot paths
    ├── virtualization/
    │   ├── __init__.py  # public VM dispatcher
    │   ├── shared.py    # constants and common validation
    │   ├── state.py     # persisted operation state and rollback
    │   ├── preflight.py # readiness checks and resource defaults
    │   └── lifecycle.py # prepare, create, delete, snapshots, status
    ├── gaming/
    │   ├── __init__.py   # public gaming tool export and dispatcher
    │   ├── library.py    # Steam library discovery
    │   ├── reports.py    # ProtonDB/PCGamingWiki fetch and cache
    │   └── settings.py   # MangoHud and Steam launch options
    ├── containers/
    │   ├── __init__.py  # public container tool exports
    │   ├── distrobox.py # distrobox lifecycle, exec, and app export
    │   ├── quadlet.py   # user systemd quadlet unit management
    │   └── podman.py    # direct podman container operations
    ├── system/
    │   ├── __init__.py  # public system info, diagnostics, and snapshot exports
    │   ├── info.py      # OS, kernel, CPU, GPU, memory, and sensor reporting
    │   ├── diagnostics.py # storage diagnostics and health checks
    │   └── snapshots.py # snapper listing, status, and diffs
    └── services/
        ├── __init__.py  # public service, firewall, and network exports
        ├── systemd.py   # systemctl lifecycle and listing
        ├── firewall.py  # firewalld mutations and reload
        └── network.py   # NetworkManager status and connection changes

skills/
└── bazzite-operator/
    ├── SKILL.md               # Triggering metadata and operator guidance
    ├── agents/openai.yaml     # UI metadata
    └── references/
        ├── install-policy.md
        ├── tool-routing.md
        ├── troubleshooting.md
        ├── dev-environments.md
        └── game-optimization.md
```

## Console scripts

The package publishes two console commands:

- `bazzite-mcp` — starts the MCP server (`stdio` transport)
- `bazzite-mcp-cleanup` — removes local cache/audit/config data

## Storage

SQLite data in `~/.local/share/bazzite-mcp/`:

- **audit_log.db** — every mutating command with timestamp, args, output, and rollback command
- **docs_cache.db** — retained for community gaming report cache

## Config

`~/.config/bazzite-mcp/config.toml` plus optional env file loading.

## Dependencies

`fastmcp, httpx, vdf`

Python 3.11+.
