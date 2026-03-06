from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def _is_kde() -> bool:
    import os

    return "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def _get_display_config() -> str:
    """Query current display setup."""
    if _is_kde():
        result = run_command("kscreen-doctor -o")
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    result = run_command("gnome-randr")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout

    return "No display tool available (kscreen-doctor for KDE, gnome-randr for GNOME)"


def _set_display_config_kde(
    quoted_output: str,
    output: str,
    resolution: str | None,
    refresh: str | None,
    scale: str | None,
) -> str:
    """Apply display config changes via kscreen-doctor (KDE Wayland)."""
    probe = run_command("kscreen-doctor -o")
    if probe.returncode != 0:
        raise ToolError(f"kscreen-doctor failed: {probe.stderr}")

    output_idx = None
    for line in probe.stdout.splitlines():
        if f" {output} " in line or line.strip().endswith(output):
            parts = line.split()
            for part in parts:
                if part.isdigit():
                    output_idx = part
                    break
            break
    if output_idx is None:
        raise ToolError(
            f"Output '{output}' not found in kscreen-doctor. "
            f"Available:\n{probe.stdout}"
        )

    changes: list[str] = []

    if resolution and refresh:
        mode_str = f"{resolution}@{refresh}"
        changes.append(f"output.{output_idx}.mode.{mode_str}")
    elif resolution:
        changes.append(f"output.{output_idx}.mode.{resolution}")
    elif refresh:
        changes.append(f"output.{output_idx}.mode.{refresh}")

    if scale:
        changes.append(f"output.{output_idx}.scale.{shlex.quote(scale)}")

    if not changes:
        raise ToolError("No resolution, refresh, or scale specified.")

    cmd = "kscreen-doctor " + " ".join(changes)
    result = run_audited(
        cmd,
        tool="display_config",
        args={
            "output": output,
            "resolution": resolution,
            "refresh": refresh,
            "scale": scale,
            "via": "kscreen-doctor",
        },
    )
    if result.returncode != 0:
        raise ToolError(f"kscreen-doctor failed: {result.stderr}")

    return (
        f"Display '{output}' configured via kscreen-doctor: "
        f"resolution={resolution}, refresh={refresh}, scale={scale}"
    )


def _set_display_config(
    output: str,
    resolution: str | None = None,
    refresh: str | None = None,
    scale: str | None = None,
) -> str:
    """Change display resolution, refresh rate, or scaling."""
    quoted_output = shlex.quote(output)

    if _is_kde():
        return _set_display_config_kde(
            quoted_output, output, resolution, refresh, scale
        )

    if scale:
        result = run_audited(
            f"gsettings set org.gnome.desktop.interface text-scaling-factor {shlex.quote(scale)}",
            tool="display_config",
            args={"output": output, "scale": scale},
        )
        if result.returncode != 0:
            raise ToolError(f"Failed to set scale: {result.stderr}")

    cmd = f"gnome-randr modify {quoted_output}"
    if resolution:
        cmd += f" --mode {shlex.quote(resolution)}"
    if refresh:
        cmd += f" --rate {shlex.quote(refresh)}"

    if resolution or refresh:
        result = run_audited(
            cmd,
            tool="display_config",
            args={"output": output, "resolution": resolution, "refresh": refresh},
        )
        if result.returncode != 0:
            raise ToolError(f"Failed to set display config: {result.stderr}")

    return (
        f"Display '{output}' configured: "
        f"resolution={resolution}, refresh={refresh}, scale={scale}"
    )


def display_config(
    action: Literal["get", "set"],
    output: str | None = None,
    resolution: str | None = None,
    refresh: str | None = None,
    scale: str | None = None,
) -> str:
    """Query or change display resolution, refresh rate, or scaling."""
    if action == "get":
        return _get_display_config()
    if action == "set":
        if not output:
            raise ToolError("'output' is required for action='set'.")
        return _set_display_config(output, resolution, refresh, scale)
    raise ToolError(f"Unknown action '{action}'.")
