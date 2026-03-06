from __future__ import annotations

from typing import Literal

from bazzite_mcp.runner import ToolError, run_command


def _snapshot_list() -> str:
    """List btrfs snapshots of the home directory."""
    result = run_command(
        "snapper -c home list --columns number,date,description,cleanup"
    )
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def _snapshot_status() -> str:
    """Show snapshot system status: retention policy, timer state, snapshot count."""
    lines: list[str] = []

    config_result = run_command("snapper -c home get-config")
    if config_result.returncode == 0:
        lines.append("RETENTION POLICY")
        for cfg_line in config_result.stdout.splitlines():
            if "TIMELINE_LIMIT" in cfg_line or "SPACE_LIMIT" in cfg_line:
                lines.append(f"  {cfg_line.strip()}")
        lines.append("")

    timeline_result = run_command("systemctl is-active snapper-timeline.timer")
    cleanup_result = run_command("systemctl is-active snapper-cleanup.timer")
    lines.append("TIMERS")
    lines.append(f"  snapper-timeline: {timeline_result.stdout.strip()}")
    lines.append(f"  snapper-cleanup:  {cleanup_result.stdout.strip()}")
    lines.append("")

    list_result = run_command("snapper -c home list --columns number,date,cleanup")
    if list_result.returncode == 0:
        count = sum(
            1
            for line in list_result.stdout.splitlines()
            if line.strip() and not line.startswith("#") and "─" not in line
        )
        lines.append(f"SNAPSHOTS: {count} total")

    return "\n".join(lines)


def _snapshot_diff(snapshot_id: int) -> str:
    """Show what files changed between a snapshot and the current state."""
    safe_id = max(1, int(snapshot_id))
    result = run_command(f"snapper -c home status {safe_id}..0")
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def manage_snapshots(
    action: Literal["list", "status", "diff"],
    snapshot_id: int | None = None,
) -> str:
    """Manage btrfs home snapshots: list, status, or diff against current state."""
    if action == "list":
        return _snapshot_list()
    if action == "status":
        return _snapshot_status()
    if action == "diff":
        if snapshot_id is None:
            raise ToolError("'snapshot_id' is required for action='diff'.")
        return _snapshot_diff(snapshot_id)
    raise ToolError(f"Unknown action '{action}'.")
