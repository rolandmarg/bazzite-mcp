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
        rollback="gsettings set org.gnome.desktop.interface color-scheme 'default'",
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


def _set_power_profile(profile: str) -> str:
    """Switch power profile between performance, balanced, or power-saver."""
    result = run_audited(
        f"powerprofilesctl set {profile}",
        tool="quick_setting",
        args={"profile": profile},
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to set power profile: {result.stderr}")
    return f"Power profile set to: {profile}"


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
