# bazzite-mcp

MCP server that gives AI agents native awareness and control of [Bazzite OS](https://bazzite.gg/).

Instead of stuffing OS knowledge into static prompt files, bazzite-mcp exposes **47 tools** that AI agents can call to query system state, install packages, manage services, change settings, and more — all following [official Bazzite best practices](https://docs.bazzite.gg/).

Works with any MCP-compatible client: [Claude Code](https://claude.com/claude-code), [OpenCode](https://github.com/opencode-ai/opencode), Cursor, etc.

## Features

- **Smart package management** — follows Bazzite's 6-tier install hierarchy (ujust > flatpak > brew > distrobox > AppImage > rpm-ostree)
- **System settings** — theme, audio output, display config, power profile, gsettings
- **Services & networking** — systemd, NetworkManager, firewalld, Tailscale
- **Containers** — Distrobox, Quadlet, Podman, Waydroid
- **System diagnostics** — hardware info, disk usage, journal logs, process list
- **Bazzite docs** — offline-capable full-text search of docs.bazzite.gg with FTS5
- **Changelog tracking** — query what changed between Bazzite releases
- **Audit log** — every mutation is logged with timestamp, command, and rollback command
- **Guardrails** — blocks destructive operations (rm -rf /, rpm-ostree reset, DE rebasing)
- **Self-improving** — agents can file GitHub issues and PRs to improve the server itself

## Install

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

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
      "command": "uv",
      "args": ["run", "--directory", "/path/to/bazzite-mcp", "python", "-m", "bazzite_mcp"]
    }
  }
}
```

### OpenCode

Add to your OpenCode MCP config with the same command/args pattern.

### Other MCP clients

Any client supporting stdio transport can use the same `uv run` command.

## Tools

### ujust (Tier 1)
| Tool | Description |
|------|-------------|
| `ujust_run` | Execute a ujust command |
| `ujust_list` | List available ujust commands, optionally filtered |
| `ujust_show` | Show source of a ujust command before running |

### Package Management
| Tool | Description |
|------|-------------|
| `install_package` | Smart installer using 6-tier hierarchy |
| `remove_package` | Remove via original install method |
| `search_package` | Search across ujust, flatpak, brew |
| `list_packages` | List installed packages by source |
| `update_packages` | Update packages or full system |

### System Settings
| Tool | Description |
|------|-------------|
| `set_theme` | Switch light/dark/auto |
| `set_audio_output` | Switch audio output device |
| `get_display_config` | Query display setup |
| `set_display_config` | Change resolution/refresh/scale |
| `set_power_profile` | Switch power profile |
| `get_settings` / `set_settings` | Read/write gsettings |

### Services & Networking
| Tool | Description |
|------|-------------|
| `manage_service` | Start/stop/enable/disable systemd services |
| `service_status` / `list_services` | Query service state |
| `network_status` | Show connections and IP info |
| `manage_connection` | Manage NetworkManager connections |
| `manage_firewall` | Manage firewalld rules |
| `manage_tailscale` | Tailscale up/down/status |

### Containers
| Tool | Description |
|------|-------------|
| `create_distrobox` | Create distrobox (Ubuntu, Fedora, Arch, etc.) |
| `manage_distrobox` | Stop/remove containers |
| `list_distroboxes` | List containers with status |
| `exec_in_distrobox` | Run command inside a container |
| `export_distrobox_app` | Export GUI app to host menu |
| `manage_quadlet` | Manage persistent container services |
| `manage_podman` | Podman operations |
| `manage_waydroid` | Android app support |

### System Info
| Tool | Description |
|------|-------------|
| `system_info` | OS, kernel, desktop, hardware summary |
| `disk_usage` | Disk space per mount |
| `update_status` | Pending updates and deployments |
| `journal_logs` | Query journalctl with filtering |
| `hardware_info` | Detailed hardware report |
| `process_list` | Top processes by CPU/memory |

### Knowledge & Docs
| Tool | Description |
|------|-------------|
| `query_bazzite_docs` | Full-text keyword search cached docs |
| `semantic_search_docs` | Semantic similarity search (requires embedding API key) |
| `bazzite_changelog` | Release changelogs |
| `install_policy` | Explain recommended install method |
| `refresh_docs_cache` | Refresh cache from docs.bazzite.gg + generate embeddings |

### Audit
| Tool | Description |
|------|-------------|
| `audit_log_query` | Query action history with rollback commands |
| `rollback_action` | Undo a specific action |

### Self-Improvement
| Tool | Description |
|------|-------------|
| `suggest_improvement` | File a GitHub issue for missing features |
| `contribute_fix` | Create a PR with code changes |
| `list_improvements` | List open improvement suggestions |
| `list_pending_prs` | List open PRs |
| `get_server_source` | Read the server's own source code |

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
| `bazzite://docs/index` | Index of all cached documentation pages |
| `bazzite://server/info` | Server config and cache status |

## Auto-Refresh (Optional)

A systemd user timer can keep the docs cache fresh automatically:

```bash
cp contrib/systemd/bazzite-mcp-refresh.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now bazzite-mcp-refresh.timer
```

Manual refresh: call the `refresh_docs_cache` tool, or run directly:

```bash
uv run --directory /path/to/bazzite-mcp python -m bazzite_mcp.refresh
```

## Semantic Search (Optional)

Set a Gemini API key (free) to enable meaning-based doc search:

```bash
export GEMINI_API_KEY="your-key"  # Get free at https://aistudio.google.com/apikey
```

Embeddings are generated during `refresh_docs_cache` and stored locally. Subsequent searches are fast local lookups. Without an API key, `semantic_search_docs` falls back to keyword search.

Default provider is Gemini (`gemini-embedding-001`, free tier). Also supports OpenAI:

```toml
# ~/.config/bazzite-mcp/config.toml

# Gemini (default, free)
embedding_provider = "gemini"
embedding_model = "gemini-embedding-001"
embedding_api_key_env = "GEMINI_API_KEY"
embedding_dimensions = 768

# Or OpenAI
# embedding_provider = "openai"
# embedding_model = "text-embedding-3-small"
# embedding_api_key_env = "OPENAI_API_KEY"
# embedding_dimensions = 512
```

## Configuration

Optional config file at `~/.config/bazzite-mcp/config.toml`:

```toml
repo_slug = "rolandmarg/bazzite-mcp"
cache_ttl_days = 7
crawl_max_pages = 100
```

Environment variable overrides:

| Variable | Default | Description |
|----------|---------|-------------|
| `BAZZITE_MCP_REPO` | `rolandmarg/bazzite-mcp` | GitHub repo slug for issues/PRs |
| `BAZZITE_MCP_LOCAL` | Auto-detected from package path | Local repo path for source reading |
| `BAZZITE_MCP_CACHE_TTL` | `7` | Cache TTL in days |
| `BAZZITE_MCP_CRAWL_MAX` | `100` | Max pages to crawl |

## Development

```bash
uv sync
uv run pytest tests/ -v
```

## License

[MIT](LICENSE)
