# bazzite-mcp

MCP server and companion skill content for giving AI agents native awareness and control of [Bazzite OS](https://bazzite.gg/).

Instead of stuffing OS knowledge into the MCP runtime, bazzite-mcp exposes **25 tools** (via action-dispatch pattern) that AI agents can call to query system state, install packages, manage services, change settings, and more. Bazzite-specific policy and workflow guidance now lives in the repo-local skill layer.

Works with any MCP-compatible client: [Claude Code](https://claude.com/claude-code), [OpenCode](https://github.com/opencode-ai/opencode), Cursor, etc.

The repository now uses a strict naming split:

- `snake_case` for Python importable code under `src/bazzite_mcp/`
- `kebab-case` for human-facing docs and skills under `docs/` and `skills/`

The repo boundary is:

- `src/bazzite_mcp/` for the MCP capability layer
- `skills/bazzite-operator/` for workflow and policy guidance

## Features

- **Package management backends** — explicit search, install, removal, inventory, and updates across ujust, flatpak, brew, and rpm-ostree
- **System settings** — theme, audio output, display config, power profile, gsettings
- **Services & networking** — systemd, NetworkManager, firewalld, Tailscale
- **Containers** — Distrobox, Quadlet, Podman
- **Virtualization** — libvirt/KVM setup, VM lifecycle, snapshots, and hardened defaults
- **System diagnostics** — hardware info, storage breakdown, security/health checks, journal logs, snapshots
- **Desktop automation** — screenshots, window management, AT-SPI accessibility interaction, keyboard/mouse input
- **Gaming** — Steam library, ProtonDB/PCGamingWiki reports, MangoHud settings
- **Bazzite docs** — offline-capable full-text search of docs.bazzite.gg with FTS5 and synonym expansion
- **Changelog tracking** — query what changed between Bazzite releases
- **Audit log** — every mutation is logged with timestamp, command, and rollback command
- **Guardrails** — command allowlist + blocklist defense-in-depth (blocks destructive ops, injection vectors, exfiltration)
- **Repo-local skill** — `bazzite-operator` captures Bazzite workflow and policy guidance
- **Graceful lifecycle** — signal handlers, resource cleanup, and clean uninstall utility

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

Package links:

- PyPI: https://pypi.org/project/bazzite-mcp/
- GitHub: https://github.com/rolandmarg/bazzite-mcp

Install from PyPI:

```bash
uv tool install bazzite-mcp
```

Verify:

```bash
bazzite-mcp --version
```

### Upgrade

```bash
uv tool upgrade bazzite-mcp
```

### Uninstall

Optionally remove cached data and config first:

```bash
bazzite-mcp-cleanup --include-config
```

Then uninstall the tool:

```bash
uv tool uninstall bazzite-mcp
```

### Install from source (development)

```bash
git clone https://github.com/rolandmarg/bazzite-mcp.git
cd bazzite-mcp
uv sync
```

## Configure your MCP client

### Claude Code

Add to `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "bazzite": {
      "command": "bazzite-mcp"
    }
  }
}
```

### OpenCode

Add to OpenCode MCP config using the same command.

### Other MCP clients

Any client supporting stdio transport can use `bazzite-mcp` as the command.

If you run from a source checkout instead of a tool install, use:

```bash
uv run --directory /path/to/bazzite-mcp python -m bazzite_mcp
```

## Skills

The repo includes a local skill at `skills/bazzite-operator/`.

Use the skill for:

- choosing between `ujust`, `flatpak`, `brew`, `distrobox`, `AppImage`, and `rpm-ostree`
- Bazzite-specific troubleshooting and service-diagnosis workflows
- development-environment setup patterns
- gaming optimization workflows

Use MCP tools for:

- live state inspection
- guarded host changes
- docs search and changelog retrieval
- audit and rollback

See `docs/architecture.md` for the boundary and `skills/bazzite-operator/` for the first extracted workflow layer.

## Tools

Tools use an action-dispatch pattern — each tool handles multiple related operations via an `action` parameter.

### Core
| Tool | Actions | Description |
|------|---------|-------------|
| `ujust` | `run`, `list`, `show` | Bazzite's built-in command runner (Tier 1) |
| `packages` | `install`, `remove`, `search`, `list`, `update` | Explicit package backend operations |
| `docs` | `search`, `changelog`, `refresh` | Bazzite docs search, changelogs, and cache refresh |
| `audit` | `query`, `rollback` | Query audit log and undo actions |

### System
| Tool | Actions | Description |
|------|---------|-------------|
| `system_info` | `basic`, `full` | OS/kernel/GPU summary or full hardware report |
| `storage_diagnostics` | — | Full storage breakdown with optimization suggestions |
| `system_doctor` | — | Security and health checks (PASS/WARN/FAIL) |
| `manage_snapshots` | `list`, `status`, `diff` | Btrfs home snapshots via snapper |

### Settings
| Tool | Actions | Description |
|------|---------|-------------|
| `quick_setting` | theme, audio, power | One-call theme/audio/power switching |
| `display_config` | `get`, `set` | Query or change resolution/refresh/scale |
| `gsettings` | `get`, `set` | Read/write GNOME gsettings |

### Desktop Automation
| Tool | Actions | Description |
|------|---------|-------------|
| `screenshot` | — | Capture desktop as AI-vision-ready JPEG |
| `manage_windows` | `list`, `activate`, `inspect` | List/focus/inspect windows via KWin + AT-SPI |
| `interact` | — | Click buttons, toggle checkboxes via AT-SPI |
| `set_text` | — | Set text in editable fields via AT-SPI |
| `send_input` | `keys`, `key`, `mouse` | Keyboard/mouse input via ydotool |

### Services & Networking
| Tool | Actions | Description |
|------|---------|-------------|
| `manage_service` | `start`, `stop`, `restart`, `enable`, `disable`, `enable_now`, `disable_now`, `status`, `list` | Systemd service management |
| `manage_firewall` | `list`, `add_port`, `remove_port`, `add_service`, `remove_service` | Firewalld rules |
| `manage_network` | `status`, `show`, `up`, `down`, `delete`, `modify`, `tailscale` | NetworkManager + Tailscale |

### Containers
| Tool | Actions | Description |
|------|---------|-------------|
| `manage_distrobox` | `create`, `list`, `enter`, `stop`, `remove`, `exec`, `export` | Full distrobox lifecycle |
| `manage_quadlet` | `list`, `create`, `start`, `stop`, `status`, `remove` | Persistent container services |
| `manage_podman` | `run`, `stop`, `rm`, `pull`, `ps`, `images`, `logs`, `inspect`, `exec` | Podman operations |

### Virtualization
| Tool | Actions | Description |
|------|---------|-------------|
| `manage_vm` | `prepare`, `preflight`, `rollback`, `setup`, `status`, `list`, `create_default`, `start`, `stop`, `delete`, `snapshot_list`, `snapshot_create`, `snapshot_revert` | libvirt/KVM VM setup with atomic prepare/rollback and hardened lifecycle management |

### Gaming
| Tool | Actions | Description |
|------|---------|-------------|
| `gaming` | `library`, `reports`, `settings_get`, `settings_set` | Steam library, ProtonDB reports, MangoHud config |

## Policy Boundary

The install hierarchy and workflow rules are no longer exposed by MCP. They live in the skill layer under `skills/bazzite-operator/`.

## MCP Resources

Resources provide read-only context that agents can query without calling tools:

| URI | Description |
|-----|-------------|
| `bazzite://system/overview` | Current OS, kernel, desktop, hardware |
| `bazzite://docs/index` | Index of all cached documentation pages |
| `bazzite://server/info` | Server config, cache status, and version |

## On-Demand Refresh (Default)

`docs(action='search')` automatically refreshes the docs cache when it is empty or stale. Default cache TTL is 12 hours.

You can still pre-warm in the background with an optional systemd timer:

```bash
cp contrib/systemd/bazzite-mcp-refresh.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now bazzite-mcp-refresh.timer
```

Manual refresh is still available via `docs(action='refresh')`, or directly:

```bash
bazzite-mcp-refresh
```

From source checkout:

```bash
uv run --directory /path/to/bazzite-mcp python -m bazzite_mcp.refresh
```

## Configuration

Optional config file at `~/.config/bazzite-mcp/config.toml`:

```toml
cache_ttl_hours = 12
crawl_max_pages = 100
```

Environment variable overrides:

| Variable | Default | Description |
|----------|---------|-------------|
| `BAZZITE_MCP_CACHE_TTL_HOURS` | `12` | Cache TTL in hours (preferred) |
| `BAZZITE_MCP_CACHE_TTL` | `7` | Cache TTL in days (legacy fallback) |
| `BAZZITE_MCP_CRAWL_MAX` | `100` | Max pages to crawl |
| `BAZZITE_MCP_ENV_FILE` | `~/.config/bazzite-mcp/env` | Path to env file loaded at startup |

## Data cleanup

Preview what would be removed:

```bash
bazzite-mcp-cleanup --dry-run
```

Remove docs cache and audit log:

```bash
bazzite-mcp-cleanup
```

Also remove config files:

```bash
bazzite-mcp-cleanup --include-config
```

From source checkout:

```bash
uv run --directory /path/to/bazzite-mcp python -m bazzite_mcp.cleanup --include-config
```

## Development

```bash
uv sync
uv run pytest tests/ -v
```

## Roadmap

- [ ] **Smithery listing** — publish as a local stdio MCP server for easier discovery
- [ ] **Signed release flow** — add package signing and provenance docs for published artifacts

## License

[MIT](LICENSE)
