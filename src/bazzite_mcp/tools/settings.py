from bazzite_mcp.runner import run_command


def set_theme(mode: str) -> str:
    """Switch between light, dark, or auto color scheme."""
    schemes = {
        "dark": "prefer-dark",
        "light": "prefer-light",
        "auto": "default",
    }
    if mode not in schemes:
        return f"Unknown mode '{mode}'. Supported: dark, light, auto."

    scheme = schemes[mode]
    result = run_command(
        f"gsettings set org.gnome.desktop.interface color-scheme '{scheme}'"
    )
    if result.returncode != 0:
        return f"Failed to set theme: {result.stderr}"
    return f"Theme set to {mode} (color-scheme: {scheme})"


def set_audio_output(device: str | None = None) -> str:
    """Switch audio output device, or list sinks when device is omitted."""
    if device is None:
        result = run_command("pactl list sinks short")
        return f"Available audio outputs:\n{result.stdout}\n\nUse sink name or index to switch."

    result = run_command(f"pactl set-default-sink {device}")
    if result.returncode != 0:
        return f"Failed to switch audio: {result.stderr}"
    return f"Audio output switched to: {device}"


def get_display_config() -> str:
    """Query current display setup."""
    result = run_command(
        "gnome-randr 2>/dev/null || xrandr --query 2>/dev/null || echo 'No display tool available'"
    )
    return result.stdout


def set_display_config(
    output: str,
    resolution: str | None = None,
    refresh: str | None = None,
    scale: str | None = None,
) -> str:
    """Change display resolution, refresh rate, or scaling."""
    if scale:
        result = run_command(
            f"gsettings set org.gnome.desktop.interface text-scaling-factor {scale}"
        )
        if result.returncode != 0:
            return f"Failed to set scale: {result.stderr}"

    cmd = f"gnome-randr modify {output}"
    if resolution:
        cmd += f" --mode {resolution}"
    if refresh:
        cmd += f" --rate {refresh}"

    if resolution or refresh:
        result = run_command(cmd)
        if result.returncode != 0:
            fallback = f"xrandr --output {output}"
            if resolution:
                fallback += f" --mode {resolution}"
            if refresh:
                fallback += f" --rate {refresh}"
            result = run_command(fallback)
            if result.returncode != 0:
                return f"Failed to set display config: {result.stderr}"

    return (
        f"Display '{output}' configured: "
        f"resolution={resolution}, refresh={refresh}, scale={scale}"
    )


def set_power_profile(profile: str) -> str:
    """Switch power profile."""
    valid = ["performance", "balanced", "power-saver"]
    if profile not in valid:
        return f"Unknown profile '{profile}'. Supported: {', '.join(valid)}."

    result = run_command(f"powerprofilesctl set {profile}")
    if result.returncode != 0:
        return f"Failed to set power profile: {result.stderr}"
    return f"Power profile set to: {profile}"


def get_settings(schema: str, key: str) -> str:
    """Read a gsettings value."""
    result = run_command(f"gsettings get {schema} {key}")
    if result.returncode != 0:
        return f"Error reading {schema} {key}: {result.stderr}"
    return result.stdout


def set_settings(schema: str, key: str, value: str) -> str:
    """Write a gsettings value."""
    result = run_command(f"gsettings set {schema} {key} {value}")
    if result.returncode != 0:
        return f"Error setting {schema} {key}: {result.stderr}"
    return f"Set {schema} {key} = {value}"
