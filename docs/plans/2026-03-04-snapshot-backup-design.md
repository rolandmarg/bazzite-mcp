# Snapshot Backup System Design

## Context

Bazzite ships snapper + btrfs-assistant pre-installed. The home directory lives on a btrfs subvolume (`home`, subvolid 257). Snapper timers exist but are disabled with no configs created.

A previous AI session set up rsync-based home backups that accumulated 245 GB of redundant copies. This design replaces that with btrfs snapshots — instant, copy-on-write, and space-efficient.

## Decision: Snapper (not btrbk, not raw btrfs)

- Already installed in Bazzite base image (not layered)
- D-Bus interface allows unprivileged reads (no sudo for MCP)
- btrfs-assistant provides GUI for browsing/restoring
- Built-in timeline + cleanup timers handle lifecycle automatically

## Snapper Configuration

- Config name: `home`
- Subvolume: `/home`
- Snapshots stored at: `/home/.snapshots/`
- Timeline: create hourly
- Retention: 5 hourly, 7 daily, 2 weekly, 0 monthly, 0 yearly
- Typical overhead: 1-5 GB for normal desktop use

## MCP Integration (read-only)

Three new tools in `tools/system.py`:

### `snapshot_list()`
- Calls `snapper -c home list --columns number,date,description,cleanup`
- Returns snapshot table as plain text

### `snapshot_status()`
- Calls `snapper -c home get-config` for retention settings
- Checks `systemctl is-active snapper-timeline.timer` for timer state
- Returns compact summary

### `snapshot_diff(snapshot_id: int)`
- Calls `snapper -c home status <id>..0`
- Returns file-level diff (added/modified/deleted) between snapshot and current state

### Guardrails
- Add `snapper` to `ALLOWED_COMMAND_PREFIXES`

### Registration
- Import and register all three tools in `server.py`

## Out of Scope

- No create/delete/restore via MCP (mutations stay with CLI/GUI)
- No external drive backup (can add btrfs send later)
- No system/root snapshots (rpm-ostree handles OS rollback)

## Files Changed

1. `src/bazzite_mcp/guardrails.py` — add `snapper` to allowlist
2. `src/bazzite_mcp/tools/system.py` — add 3 snapshot tools
3. `src/bazzite_mcp/server.py` — import and register tools
