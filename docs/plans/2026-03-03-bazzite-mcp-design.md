# Bazzite MCP Server — Design Document

**Date:** 2026-03-03
**Status:** Approved

## Overview

A custom MCP (Model Context Protocol) server that serves as a native translation layer between AI agents and the Bazzite OS. Replaces static AGENTS.md OS knowledge with live, queryable tools that can both inform and act.

## Goals

- Any MCP-compatible client (Claude Code, OpenCode, Cursor, etc.) can use it
- Execute system operations directly (not just return commands)
- Serve Bazzite documentation offline via local cache
- Track changelogs between Bazzite releases
- Maintain an audit log of all mutations with rollback commands
- Follow official Bazzite best practices from docs.bazzite.gg

## Architecture

- **Language:** Python 3.14 + FastMCP
- **Transport:** stdio (standard for local MCP servers)
- **Storage:** SQLite (docs cache + audit log)
- **Package management:** uv (installed via brew)
- **Architecture style:** Monolithic — single FastMCP server with tool groups as Python modules

```
┌─────────────────────────────────────────────────┐
│              bazzite-mcp server                 │
│            (Python + FastMCP)                   │
│                                                 │
│  ┌───────────┐ ┌───────────┐ ┌───────────────┐ │
│  │  ujust    │ │ packages  │ │   settings    │ │
│  │  tools    │ │  tools    │ │    tools      │ │
│  └───────────┘ └───────────┘ └───────────────┘ │
│  ┌───────────┐ ┌───────────┐ ┌───────────────┐ │
│  │ services  │ │containers │ │    system     │ │
│  │  tools    │ │  tools    │ │    tools      │ │
│  └───────────┘ └───────────┘ └───────────────┘ │
│  ┌───────────┐ ┌───────────┐                   │
│  │   docs    │ │  audit    │                   │
│  │  tools    │ │  tools    │                   │
│  └───────────┘ └───────────┘                   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │     docs_cache.db (SQLite + FTS5)       │   │
│  └─────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────┐   │
│  │     audit_log.db (SQLite)               │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
         ▲                           ▲
         │ stdio                     │ stdio
    ┌────┴────┐                 ┌────┴────┐
    │ Claude  │                 │OpenCode │
    │  Code   │                 │/others  │
    └─────────┘                 └─────────┘
```

## Bazzite Install Policy (Official, from docs.bazzite.gg)

The MCP server enforces this 6-tier hierarchy:

1. **ujust** — Bazzite's custom command runner. Check first for setup/install/configure commands.
2. **Flatpak** (via Bazaar/Flathub) — Primary method for GUI applications. Sandboxed.
3. **Homebrew** — CLI/TUI tools only. No GUI apps (use Flatpak for those).
4. **Containers** — Distrobox for package managers from other distros; Quadlet for persistent services.
5. **AppImage** — Portable apps from trusted sources. Manage via Gear Lever.
6. **rpm-ostree** — **Last resort.** Can freeze updates, block rebasing, cause dependency conflicts. Warn strongly before use.

### Key Bazzite Warnings
- rpm-ostree layering can pause system updates and prevent rebasing
- Do NOT rebase to switch desktop environments — backup and reinstall instead
- Hostname must be ≤20 characters (breaks Distrobox)
- Download AppImages only from trusted sources

## Tool Catalog

### ujust Tools
| Tool | Description |
|------|-------------|
| `ujust_run` | Execute a ujust command |
| `ujust_list` | List available ujust commands, optionally filtered by keyword |
| `ujust_show` | Show source script of a ujust command before running |

### Package Management Tools
| Tool | Description |
|------|-------------|
| `install_package` | Smart installer using 6-tier hierarchy. Returns method chosen and reasoning. Warns before rpm-ostree. |
| `remove_package` | Remove a package via the method it was installed with |
| `search_package` | Search across ujust, flatpak, brew, rpm repos with tier recommendations |
| `list_packages` | List installed packages, filterable by source |
| `update_packages` | Update packages for a given source, or `ujust update` for full system |

### System Settings Tools
| Tool | Description |
|------|-------------|
| `set_theme` | Switch light/dark/auto mode (GNOME/KDE aware) |
| `set_audio_output` | Switch audio output device |
| `get_display_config` | Query current display setup |
| `set_display_config` | Change resolution, refresh rate, scaling |
| `set_power_profile` | Switch power profile (performance/balanced/power-saver) |
| `get_settings` | Read any gsettings/dconf key |
| `set_settings` | Write any gsettings/dconf key |

### Services & Networking Tools
| Tool | Description |
|------|-------------|
| `manage_service` | Start/stop/restart/enable/disable systemd services (user and system) |
| `service_status` | Get status of a systemd service |
| `list_services` | List services, filterable by state |
| `network_status` | Show NetworkManager connections, active interfaces, IP info |
| `manage_connection` | Create/modify/delete NetworkManager connections |
| `manage_firewall` | Open/close ports, list firewalld rules |
| `manage_tailscale` | Tailscale up/down/status/set |

### Container & Dev Environment Tools
| Tool | Description |
|------|-------------|
| `create_distrobox` | Create a distrobox container (Ubuntu, Fedora, Arch, etc.) |
| `manage_distrobox` | Enter/stop/remove distrobox containers |
| `list_distroboxes` | List existing distrobox containers with status |
| `exec_in_distrobox` | Run a command inside a specific distrobox |
| `export_distrobox_app` | Export a containerized GUI app to host menu |
| `manage_quadlet` | Create/manage Quadlet units for persistent services |
| `manage_podman` | Podman container operations (ps, run, stop, rm, images) |
| `manage_waydroid` | Waydroid setup/start/stop for Android apps |

### System Info & Diagnostics Tools
| Tool | Description |
|------|-------------|
| `system_info` | OS version, kernel, desktop, hardware summary |
| `disk_usage` | Disk space per mount, largest directories |
| `update_status` | Pending updates, rpm-ostree status, staged deployments |
| `journal_logs` | Query journalctl with filtering (unit, priority, time range) |
| `hardware_info` | Detailed hardware report (CPU, GPU, RAM, sensors) |
| `process_list` | Top processes by CPU/memory |

### Knowledge & Docs Tools
| Tool | Description |
|------|-------------|
| `query_bazzite_docs` | Full-text search the cached Bazzite documentation |
| `bazzite_changelog` | Changelog for a specific version or latest N releases |
| `install_policy` | Explain recommended install method with 6-tier reasoning |
| `refresh_docs_cache` | Trigger manual refresh from docs.bazzite.gg |

### Audit & History Tools
| Tool | Description |
|------|-------------|
| `audit_log` | Query action history with rollback commands |
| `rollback_action` | Execute the rollback command for a specific audit entry |

## Guardrails (Built-in Safety)

The server refuses to execute:
- `rpm-ostree reset` (removes ALL layered packages)
- Destructive filesystem operations (`rm -rf /`, `mkfs`, etc.)
- Desktop environment rebasing (docs say backup & reinstall)
- Hostname changes >20 characters

The server warns before:
- Any `rpm-ostree install` (with explanation of risks)
- Service disabling that could affect boot
- Firewall rule changes

## Docs Cache Design

- **Storage:** SQLite with FTS5 full-text search index
- **Source:** docs.bazzite.gg pages + GitHub releases API (ublue-os/bazzite)
- **Fetch strategy:** Live fetch with local cache. Falls back to cache when offline.
- **Cache TTL:** 7 days. Stale cache still serves with staleness warning.
- **Schema:**
  - `pages` table: url, title, content, section, fetched_at
  - `changelogs` table: version, date, body
  - FTS5 virtual table for full-text search across pages

## Audit Log Design

- **Storage:** SQLite at `~/.local/share/bazzite-mcp/audit_log.db`
- **Logged:** All mutation tools (install, remove, config change, service toggle)
- **Not logged:** Read-only tools (list, status, query)
- **Schema:**
  - id, timestamp (ISO 8601), tool, command, args (JSON), result, output, rollback, client

## Project Structure

```
~/bazzite-mcp/
├── pyproject.toml              # uv project: fastmcp, httpx, beautifulsoup4
├── src/
│   └── bazzite_mcp/
│       ├── __init__.py
│       ├── server.py           # FastMCP entry point, tool registration
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── ujust.py
│       │   ├── packages.py
│       │   ├── settings.py
│       │   ├── services.py
│       │   ├── containers.py
│       │   ├── system.py
│       │   ├── docs.py
│       │   └── audit.py
│       ├── cache/
│       │   └── docs_cache.py   # SQLite FTS5 fetcher + cache
│       ├── guardrails.py       # deny-list, warnings, safety checks
│       └── db.py               # SQLite helpers
├── data/                       # runtime data (gitignored)
│   ├── docs_cache.db
│   └── audit_log.db
└── tests/
```

## Deployment

1. Install uv: `brew install uv`
2. Initialize project: `cd ~/bazzite-mcp && uv init`
3. Add dependencies: `uv add fastmcp httpx beautifulsoup4`
4. Register in Claude Code `~/.claude/mcp.json`:
   ```json
   {
     "mcpServers": {
       "bazzite": {
         "command": "uv",
         "args": ["run", "--directory", "/home/kira/bazzite-mcp", "python", "-m", "bazzite_mcp.server"]
       }
     }
   }
   ```
5. Register similarly in OpenCode and other MCP clients

## Side Effect: AGENTS.md Update

Update `~/.config/opencode/AGENTS.md` install policy to match official 6-tier hierarchy:
1. `ujust` first for setup/install/configure commands
2. `flatpak` for GUI apps (Flathub preferred)
3. `brew` for CLI/TUI tools only
4. `distrobox` for other distro package managers; `quadlet` for persistent services
5. `AppImage` from trusted sources (manage via Gear Lever)
6. `rpm-ostree` last resort only — warn about update/rebase blocking risks
