# bazzite-mcp Product Growth Design

**Date:** 2026-03-03
**Status:** Draft — shelved for future prioritization

## Context

bazzite-mcp v0.1.0 ships 47 tools covering package management, system settings, services, containers, diagnostics, docs search, and audit/rollback. It is the only distro-aware MCP server in existence (out of 18,000+ registered MCP servers). No competitor provides structured OS intelligence through MCP.

This document outlines how to grow the tool into a more complete, native-feeling OS agent.

## Current Coverage

| Domain | Tools | Maturity |
|---|---|---|
| Package management (6-tier hierarchy) | 5 | Solid |
| ujust commands | 3 | Solid |
| System settings (theme, audio, display, power) | 7 | Solid |
| Services (systemd, NetworkManager, firewall, Tailscale) | 7 | Solid |
| Containers (distrobox, quadlet, podman, waydroid) | 8 | Solid |
| System info & diagnostics | 6 | Solid |
| Docs & knowledge | 5 | Solid |
| Audit & rollback | 2 | Solid |
| Self-improvement (GitHub) | 5 | Solid |

## Growth Areas

### 1. Gaming (Identity Gap)

Bazzite is a gaming-focused OS. The MCP server has zero gaming awareness. This is the highest-impact growth area because it aligns with what makes Bazzite unique.

**Proposed tools:**

| Tool | Purpose | Backing |
|---|---|---|
| `steam_library` | List installed games, check Proton compatibility, launch | `~/.steam/` file parsing |
| `game_performance` | MangoHud config, FPS overlay toggle, Gamescope settings | Config file edits, env vars |
| `manage_lutris` | Install/configure/launch non-Steam games | Lutris CLI |
| `gamepad_config` | Controller detection, mapping, calibration | `evtest`, Steam Input |
| `gaming_diagnostics` | Shader cache status, Proton versions, Vulkan info, GPU driver | `vulkaninfo`, mesa, driver queries |
| `game_mode` | Toggle GameMode, check active optimizations | `gamemoded` CLI |

**Open questions:**
- Steam data: direct file parsing vs SteamCMD vs local IPC? TOS implications?
- How much MangoHud/Gamescope config should be structured vs raw config editing?

### 2. Hardware & Peripherals

Daily operations that currently require the Settings app or CLI knowledge.

**Proposed tools:**

| Tool | Purpose | Backing |
|---|---|---|
| `bluetooth_manage` | Scan, pair, connect, trust, remove | D-Bus (`org.bluez`) or `bluetoothctl` |
| `wifi_scan` | Scan available networks, signal strength | `nmcli device wifi list` (extends existing NM tools) |
| `screen_brightness` | Get/set backlight level | `brightnessctl` or `/sys/class/backlight/` |
| `input_devices` | List mice/keyboards/gamepads, check status | `libinput list-devices` |
| `usb_devices` | List connected USB, safe eject | `lsusb`, `udisksctl` |

**Open questions:**
- Bluetooth: D-Bus is structured but complex; `bluetoothctl` is simpler but interactive. Recommendation: D-Bus for scan/pair/connect, avoids interactive session issues.
- Should `wifi_scan` be a separate tool or extend `network_status`?

### 3. Proactive System Awareness

Move from "ask and answer" to "the agent notices things."

**Proposed tools:**

| Tool | Purpose | Backing |
|---|---|---|
| `system_health` | Composite score: disk, RAM, CPU, failed services, pending updates | Aggregates existing tool outputs + scoring |
| `pending_actions` | Summary: "3 updates available, 1 failed service, disk 87% full" | Combines update_status + service_status + disk_usage |
| `manage_timer` | Create/list/remove systemd user timers | `systemctl --user`, write unit files |

**Open questions:**
- Event subscriptions (USB plug, battery low, service crash) would be powerful but require a long-lived connection model. Does MCP's request-response pattern support this, or do we need MCP Resource Subscriptions?

### 4. Desktop Integration

Bridge the gap between CLI agent and GUI desktop.

**Proposed tools:**

| Tool | Purpose | Backing |
|---|---|---|
| `launch_app` | Open apps by name or .desktop file | `gtk-launch`, `xdg-open` |
| `clipboard` | Read/write clipboard | `wl-copy`/`wl-paste` (Wayland) |
| `notifications` | Send desktop notifications to user | `notify-send` |
| `screenshot` | Capture screen/window/region | `grim` (Wayland), `gnome-screenshot` |

**Open questions:**
- Wayland heavily restricts window management (no listing/moving windows without compositor protocols). How much is realistic without GNOME-specific extensions?
- Is `screenshot` useful without Computer Use vision? Could pair with MCP Sampling for the server to ask the LLM to interpret.

### 5. File Management

Expected OS capability that's currently absent.

**Proposed tools:**

| Tool | Purpose | Backing |
|---|---|---|
| `find_files` | Search by name, type, size, date | `fd` or `find` |
| `disk_cleanup` | Identify large files, old caches, stale data | Size analysis + known cache paths |

### 6. System State Export / Migration

Unique differentiator — reproducible Bazzite setups.

**Proposed tools:**

| Tool | Purpose | Backing |
|---|---|---|
| `export_system_state` | Dump flatpak list, brew list, dconf, distrobox configs, enabled services | Script aggregation |
| `import_system_state` | Restore from exported state | Inverse operations |

## MCP Protocol Opportunities

Features in the MCP spec not yet used:

| Feature | Opportunity | Effort |
|---|---|---|
| **Streaming results** | Progress for long ops (system update, large installs) | Low |
| **Resource Subscriptions** | Push system state changes to clients (service crash, update available) | Medium |
| **MCP Sampling** | Server asks LLM to diagnose detected issues proactively | Medium |
| **MCP Roots** | Declare managed filesystem paths | Low |

## Suggested Priority Order

1. **Gaming tools** — identity play, zero competition, clear demand from Bazzite users
2. **Hardware control** — makes agent feel like a native desktop companion
3. **System health + pending actions** — low effort, high value, builds on existing tools
4. **Scheduled tasks** (systemd timers) — enables proactive patterns
5. **Desktop integration** — bridges CLI-GUI gap
6. **Streaming results** — low effort QoL for long operations
7. **File management** — expected capability
8. **System state export/import** — unique differentiator
9. **Resource subscriptions + sampling** — advanced proactive features

## Architecture Considerations

- New tool groups follow existing pattern: `tools/<domain>.py` with functions registered on the FastMCP server
- All mutation tools must integrate with existing audit system and guardrails
- Gaming tools may warrant their own guardrails subset (e.g., allowlisting `mangohud`, `gamemoded`, `gamescope`)
- Hardware tools touching D-Bus need async support (already available via FastMCP)
- Consider whether gaming/hardware deserve separate MCP servers or stay monolithic. Recommendation: stay monolithic until tool count becomes unwieldy (80+), then consider splitting.
