# bazzite-mcp

MCP server plus local skill content for agents operating a Bazzite host.

Use it when the agent needs:

- Bazzite-native knowledge and install choices
- Live host state and guarded mutations
- Desktop awareness: screenshots, windows, input, accessibility
- Bazzite docs and changelog lookup

`src/bazzite_mcp/` is the capability layer.
`skills/bazzite-operator/` is the workflow/policy layer.

## Install

Requires Python 3.11+ and `uv`.

```bash
uv tool install bazzite-mcp
bazzite-mcp --version
```

From source:

```bash
git clone https://github.com/rolandmarg/bazzite-mcp.git
cd bazzite-mcp
uv sync
```

## MCP Setup

Claude Code:

```json
{
  "mcpServers": {
    "bazzite": {
      "command": "bazzite-mcp"
    }
  }
}
```

Any stdio-capable MCP client can use the same command.

From a source checkout:

```bash
uv run --directory /path/to/bazzite-mcp python -m bazzite_mcp
```

## Core MCP

The server exposes host capabilities for:

- packages, `ujust`, updates, audit, rollback
- system info, storage checks, snapshots, health checks
- settings: theme, audio, power, display, gsettings
- services, firewall, networking
- containers and VMs
- desktop control: screenshots, windows, AT-SPI actions, keyboard, mouse
- gaming: Steam library, reports, MangoHud settings
- docs search and changelog retrieval

Resources:

- `bazzite://system/overview`
- `bazzite://docs/index`
- `bazzite://server/info`

## Skills

The repo includes `skills/bazzite-operator/`.

Use the skill for:

- choosing the right Bazzite install path: `ujust`, Flatpak, Homebrew, Distrobox, VM, rpm-ostree
- troubleshooting Bazzite-specific desktop, service, and update issues
- turning raw MCP output into Bazzite-aware recommendations

Use MCP tools for live state and host changes. Use the skill for policy and workflow.

## Utilities

Refresh docs cache:

```bash
bazzite-mcp-refresh
```

Clean local data:

```bash
bazzite-mcp-cleanup
```

Remove config too:

```bash
bazzite-mcp-cleanup --include-config
```

## License

[MIT](LICENSE)
