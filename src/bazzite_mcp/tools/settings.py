from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def set_theme(mode: Literal["dark", "light", "auto"]) -> str:
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
        tool="set_theme",
        args={"mode": mode},
        rollback=f"gsettings set org.gnome.desktop.interface color-scheme 'default'",
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to set theme: {result.stderr}")
    return f"Theme set to {mode} (color-scheme: {scheme})"


def set_audio_output(device: str | None = None) -> str:
    """Switch audio output device, or list sinks when device is omitted."""
    if device is None:
        result = run_command("pactl list sinks short")
        return f"Available audio outputs:\n{result.stdout}\n\nUse sink name or index to switch."

    result = run_audited(
        f"pactl set-default-sink {shlex.quote(device)}",
        tool="set_audio_output",
        args={"device": device},
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to switch audio: {result.stderr}")
    return f"Audio output switched to: {device}"


def get_display_config() -> str:
    """Query current display setup."""
    result = run_command("gnome-randr")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout

    fallback = run_command("xrandr --query")
    if fallback.returncode == 0 and fallback.stdout.strip():
        return fallback.stdout

    return "No display tool available"


def set_display_config(
    output: str,
    resolution: str | None = None,
    refresh: str | None = None,
    scale: str | None = None,
) -> str:
    """Change display resolution, refresh rate, or scaling."""
    soutput = shlex.quote(output)
    if scale:
        result = run_audited(
            f"gsettings set org.gnome.desktop.interface text-scaling-factor {shlex.quote(scale)}",
            tool="set_display_config",
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
            tool="set_display_config",
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
                tool="set_display_config",
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


def set_power_profile(
    profile: Literal["performance", "balanced", "power-saver"],
) -> str:
    """Switch power profile between performance, balanced, or power-saver."""

    result = run_audited(
        f"powerprofilesctl set {profile}",
        tool="set_power_profile",
        args={"profile": profile},
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to set power profile: {result.stderr}")
    return f"Power profile set to: {profile}"


def get_settings(schema: str, key: str) -> str:
    """Read a gsettings value."""
    result = run_command(f"gsettings get {shlex.quote(schema)} {shlex.quote(key)}")
    if result.returncode != 0:
        raise ToolError(f"Error reading {schema} {key}: {result.stderr}")
    return result.stdout


def set_settings(schema: str, key: str, value: str) -> str:
    """Write a gsettings value."""
    result = run_audited(
        f"gsettings set {shlex.quote(schema)} {shlex.quote(key)} {shlex.quote(value)}",
        tool="set_settings",
        args={"schema": schema, "key": key, "value": value},
    )
    if result.returncode != 0:
        raise ToolError(f"Error setting {schema} {key}: {result.stderr}")
    return f"Set {schema} {key} = {value}"
