# bazzite-mcp

MCP server that gives AI agents native awareness and control of [Bazzite OS](https://bazzite.gg/).

Instead of stuffing OS knowledge into static prompt files, bazzite-mcp exposes **24 tools** (via action-dispatch pattern) that AI agents can call to query system state, install packages, manage services, change settings, and more — all following [official Bazzite best practices](https://docs.bazzite.gg/).

Works with any MCP-compatible client: [Claude Code](https://claude.com/claude-code), [OpenCode](https://github.com/opencode-ai/opencode), Cursor, etc.

## Features

- **Smart package management** — follows Bazzite's 6-tier install hierarchy (ujust > flatpak > brew > distrobox > AppImage > rpm-ostree)
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
- **MCP Prompts** — reusable workflow templates for troubleshooting, installing apps, optimizing games
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

## Tools

Tools use an action-dispatch pattern — each tool handles multiple related operations via an `action` parameter.

### Core
| Tool | Actions | Description |
|------|---------|-------------|
| `ujust` | `run`, `list`, `show` | Bazzite's built-in command runner (Tier 1) |
| `packages` | `install`, `remove`, `search`, `list`, `update` | Smart package management with 6-tier hierarchy |
| `docs` | `search`, `changelog`, `policy`, `refresh` | Bazzite docs search, changelogs, install policy |
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
| `manage_service` | `start`, `stop`, `restart`, `enable`, `disable`, `status`, `list` | Systemd service management |
| `manage_firewall` | `list`, `add-port`, `remove-port`, `add-service`, `remove-service` | Firewalld rules |
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

## Bazzite Install Hierarchy

The server enforces the official 6-tier hierarchy from [docs.bazzite.gg](https://docs.bazzite.gg/):

1. **ujust** — Bazzite's built-in command runner. Check first.
2. **Flatpak** — Primary method for GUI apps.
3. **Homebrew** — CLI/TUI tools only.
4. **Distrobox/Quadlet** — Other distro package managers / persistent services.
5. **AppImage** — Portable apps from trusted sources.
6. **rpm-ostree** — Last resort. Can freeze updates and block rebasing.

## MCP Resources

Resources provide read-only context that agents can query without calling tools:

| URI | Description |
|-----|-------------|
| `bazzite://system/overview` | Current OS, kernel, desktop, hardware |
| `bazzite://install/hierarchy` | Full 6-tier install hierarchy with explanations |
| `bazzite://install/policy` | Quick-reference install policy |
| `bazzite://docs/index` | Index of all cached documentation pages |
| `bazzite://server/info` | Server config, cache status, and version |

## MCP Prompts

Prompts are reusable workflow templates that agents can invoke:

| Prompt | Description |
|--------|-------------|
| `troubleshoot_system` | Gather diagnostics for a system issue |
| `install_app` | Walk through the 6-tier hierarchy to install an app |
| `setup_dev_environment` | Set up a dev environment using distrobox |
| `diagnose_service` | Debug a failing systemd service |
| `optimize_game` | Optimize a game based on hardware and community data |

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
