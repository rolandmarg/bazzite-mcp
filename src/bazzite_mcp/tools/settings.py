from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def _set_theme(mode: str) -> str:
    """Switch between light, dark, or auto color scheme (GNOME only)."""
    schemes = {
        "dark": "prefer-dark",
        "light": "prefer-light",
        "auto": "default",
    }
    if mode not in schemes:
        raise ToolError(f"Unknown mode '{mode}'. Supported: dark, light, auto.")

    scheme = schemes[mode]
    result = run_audited(
        f"gsettings set org.gnome.desktop.interface color-scheme '{scheme}'",
        tool="quick_setting",
        args={"mode": mode},
        rollback=f"gsettings set org.gnome.desktop.interface color-scheme 'default'",
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to set theme: {result.stderr}")
    return f"Theme set to {mode} (color-scheme: {scheme})"


def _set_audio_output(device: str | None = None) -> str:
    """Switch audio output device, or list sinks when device is omitted."""
    if device is None:
        result = run_command("pactl list sinks short")
        return f"Available audio outputs:\n{result.stdout}\n\nUse sink name or index to switch."

    result = run_audited(
        f"pactl set-default-sink {shlex.quote(device)}",
        tool="quick_setting",
        args={"device": device},
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to switch audio: {result.stderr}")
    return f"Audio output switched to: {device}"


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

    fallback = run_command("xrandr --query")
    if fallback.returncode == 0 and fallback.stdout.strip():
        return fallback.stdout

    return "No display tool available"


def _set_display_config(
    output: str,
    resolution: str | None = None,
    refresh: str | None = None,
    scale: str | None = None,
) -> str:
    """Change display resolution, refresh rate, or scaling."""
    soutput = shlex.quote(output)

    if _is_kde():
        return _set_display_config_kde(soutput, output, resolution, refresh, scale)

    if scale:
        result = run_audited(
            f"gsettings set org.gnome.desktop.interface text-scaling-factor {shlex.quote(scale)}",
            tool="display_config",
            args={"output": output, "scale": scale},
        )
        if result.returncode != 0:
            raise ToolError(f"Failed to set scale: {result.stderr}")

    cmd = f"gnome-randr modify {soutput}"
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
            fallback = f"xrandr --output {soutput}"
            if resolution:
                fallback += f" --mode {shlex.quote(resolution)}"
            if refresh:
                fallback += f" --rate {shlex.quote(refresh)}"
            result = run_audited(
                fallback,
                tool="display_config",
                args={
                    "output": output,
                    "resolution": resolution,
                    "refresh": refresh,
                    "via": "xrandr",
                },
            )
            if result.returncode != 0:
                raise ToolError(f"Failed to set display config: {result.stderr}")

    return (
        f"Display '{output}' configured: "
        f"resolution={resolution}, refresh={refresh}, scale={scale}"
    )


def _set_display_config_kde(
    soutput: str,
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
        args={"output": output, "resolution": resolution, "refresh": refresh, "scale": scale, "via": "kscreen-doctor"},
    )
    if result.returncode != 0:
        raise ToolError(f"kscreen-doctor failed: {result.stderr}")

    return (
        f"Display '{output}' configured via kscreen-doctor: "
        f"resolution={resolution}, refresh={refresh}, scale={scale}"
    )


def _set_power_profile(
    profile: str,
) -> str:
    """Switch power profile between performance, balanced, or power-saver."""
    result = run_audited(
        f"powerprofilesctl set {profile}",
        tool="quick_setting",
        args={"profile": profile},
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to set power profile: {result.stderr}")
    return f"Power profile set to: {profile}"


def _get_settings(schema: str, key: str) -> str:
    """Read a gsettings value."""
    result = run_command(f"gsettings get {shlex.quote(schema)} {shlex.quote(key)}")
    if result.returncode != 0:
        raise ToolError(f"Error reading {schema} {key}: {result.stderr}")
    return result.stdout


def _set_settings(schema: str, key: str, value: str) -> str:
    """Write a gsettings value."""
    result = run_audited(
        f"gsettings set {shlex.quote(schema)} {shlex.quote(key)} {shlex.quote(value)}",
        tool="gsettings",
        args={"schema": schema, "key": key, "value": value},
    )
    if result.returncode != 0:
        raise ToolError(f"Error setting {schema} {key}: {result.stderr}")
    return f"Set {schema} {key} = {value}"


# --- Dispatchers ---


def quick_setting(
    setting: Literal["theme", "audio", "power"],
    mode: Literal["dark", "light", "auto"] | None = None,
    device: str | None = None,
    profile: Literal["performance", "balanced", "power-saver"] | None = None,
) -> str:
    """Switch theme, audio output, or power profile."""
    if setting == "theme":
        if not mode:
            raise ToolError("'mode' is required for setting='theme'.")
        return _set_theme(mode)
    if setting == "audio":
        return _set_audio_output(device)
    if setting == "power":
        if not profile:
            raise ToolError("'profile' is required for setting='power'.")
        return _set_power_profile(profile)
    raise ToolError(f"Unknown setting '{setting}'.")


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


def gsettings(
    action: Literal["get", "set"],
    schema: str | None = None,
    key: str | None = None,
    value: str | None = None,
) -> str:
    """Read or write a gsettings value."""
    if not schema or not key:
        raise ToolError("'schema' and 'key' are required.")
    if action == "get":
        return _get_settings(schema, key)
    if action == "set":
        if value is None:
            raise ToolError("'value' is required for action='set'.")
        return _set_settings(schema, key, value)
    raise ToolError(f"Unknown action '{action}'.")
