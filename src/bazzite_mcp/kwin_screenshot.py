"""Per-window and per-monitor screenshot capture with coordinate metadata.

Uses spectacle CLI for capture and KWin D-Bus for window geometry.
Screenshot pixels map to portal input coordinates via the returned metadata
(origin + scale factor).
"""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from pathlib import Path

from bazzite_mcp.runner import run_command

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = Path("/tmp/bazzite-mcp")

# Regex to strip ANSI escape sequences from kscreen-doctor output
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@lru_cache(maxsize=1)
def get_monitor_info() -> dict[str, dict]:
    """Parse kscreen-doctor to get monitor positions and scales.

    Returns a dict keyed by output name, e.g.:
        {"HDMI-A-1": {"x": 2560, "y": 169, "w": 2560, "h": 1440, "scale": 1.5},
         "HDMI-A-2": {"x": 0, "y": 0, "w": 2560, "h": 1440, "scale": 1.0}}
    """
    result = run_command("kscreen-doctor --outputs")
    if result.returncode != 0:
        logger.warning("kscreen-doctor failed: %s", result.stderr)
        return {}

    text = _ANSI_RE.sub("", result.stdout)
    monitors: dict[str, dict] = {}
    current_name: str | None = None

    for line in text.splitlines():
        # Match output header: "Output: 1 HDMI-A-1 <uuid>"
        m = re.match(r"Output:\s+\d+\s+(\S+)", line)
        if m:
            current_name = m.group(1)
            monitors[current_name] = {"x": 0, "y": 0, "w": 0, "h": 0, "scale": 1.0}
            continue

        if current_name is None:
            continue

        # Match geometry: "	Geometry: 2560,169 2560x1440"
        gm = re.match(r"\s*Geometry:\s*(-?\d+),(-?\d+)\s+(\d+)x(\d+)", line)
        if gm:
            monitors[current_name]["x"] = int(gm.group(1))
            monitors[current_name]["y"] = int(gm.group(2))
            monitors[current_name]["w"] = int(gm.group(3))
            monitors[current_name]["h"] = int(gm.group(4))
            continue

        # Match scale: "	Scale: 1.5"
        sm = re.match(r"\s*Scale:\s*([0-9.]+)", line)
        if sm:
            monitors[current_name]["scale"] = float(sm.group(1))
            continue

    return monitors


def get_active_window_info() -> dict:
    """Get active window geometry from KWin.

    Returns: {"uuid": "...", "caption": "...", "x": 200, "y": 100,
              "width": 1200, "height": 900}

    Uses gdbus instead of qdbus because qdbus times out on queryWindowInfo.
    """
    result = run_command(
        "gdbus call --session --dest org.kde.KWin "
        "--object-path /KWin --method org.kde.KWin.queryWindowInfo"
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to query active window: {result.stderr}")

    info: dict = {}
    raw = result.stdout
    for key in ("uuid", "caption", "x", "y", "width", "height"):
        m = re.search(rf"'{key}':\s*<([^>]+)>", raw)
        if not m:
            continue
        val = m.group(1).strip("'")
        if key == "uuid":
            info["uuid"] = val.strip("{}")
        elif key == "caption":
            info["caption"] = val
        else:
            try:
                info[key] = int(float(val))
            except ValueError:
                info[key] = 0

    return info


def get_window_scale(window_x: float) -> float:
    """Determine scale factor based on which monitor the window is on.

    Checks which monitor's logical region contains window_x and returns
    that monitor's scale factor.
    """
    monitors = get_monitor_info()
    for _name, m in monitors.items():
        if m["x"] <= window_x < m["x"] + m["w"]:
            return m["scale"]
    # Default to 1.0 if no monitor matched
    return 1.0


def capture_active_window() -> tuple[bytes, dict]:
    """Capture active window via spectacle, return (jpeg_bytes, metadata).

    metadata = {"origin_x": <float>, "origin_y": <float>, "scale": <float>,
                "width": <int>, "height": <int>, "caption": <str>}

    origin_x/y are logical coordinates of the window's top-left corner.
    spectacle captures at physical pixel resolution, so on a scale-1.5
    monitor a 2560-logical-wide window produces a 3840-pixel-wide image.
    """
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Get window info before capture (spectacle -a captures the active window)
    win = get_active_window_info()

    timestamp = int(time.time() * 1000)
    png_path = SCREENSHOT_DIR / f"win-{timestamp}.png"
    jpg_path = png_path.with_suffix(".jpg")

    result = run_command(
        f"spectacle -a --background --nonotify --output {png_path}"
    )
    if result.returncode != 0:
        raise RuntimeError(f"spectacle capture failed: {result.stderr}")

    # Convert PNG to JPEG
    conv = run_command(f"magick {png_path} -quality 90 {jpg_path}")
    if conv.returncode != 0:
        # Fall back to PNG bytes if magick fails
        jpeg_bytes = png_path.read_bytes()
    else:
        jpeg_bytes = jpg_path.read_bytes()
        png_path.unlink(missing_ok=True)

    scale = get_window_scale(win.get("x", 0))

    metadata = {
        "origin_x": win.get("x", 0),
        "origin_y": win.get("y", 0),
        "scale": scale,
        "width": win.get("width", 0),
        "height": win.get("height", 0),
        "caption": win.get("caption", ""),
    }
    return jpeg_bytes, metadata


def capture_screen(name: str | None = None) -> tuple[bytes, dict]:
    """Capture current monitor (the one with the active window).

    If name is given it is informational only -- spectacle -m always captures
    the monitor that currently has focus.

    Returns (jpeg_bytes, metadata) where metadata includes monitor origin,
    logical size, and scale.
    """
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time() * 1000)
    png_path = SCREENSHOT_DIR / f"mon-{timestamp}.png"
    jpg_path = png_path.with_suffix(".jpg")

    result = run_command(
        f"spectacle -m --background --nonotify --output {png_path}"
    )
    if result.returncode != 0:
        raise RuntimeError(f"spectacle capture failed: {result.stderr}")

    # Convert PNG to JPEG
    conv = run_command(f"magick {png_path} -quality 90 {jpg_path}")
    if conv.returncode != 0:
        jpeg_bytes = png_path.read_bytes()
    else:
        jpeg_bytes = jpg_path.read_bytes()
        png_path.unlink(missing_ok=True)

    # Determine which monitor was captured from active window position
    win = get_active_window_info()
    monitors = get_monitor_info()

    # Find the monitor containing the active window
    mon_info = {"x": 0, "y": 0, "w": 0, "h": 0, "scale": 1.0}
    mon_name = name or "unknown"
    for mname, m in monitors.items():
        wx = win.get("x", 0)
        if m["x"] <= wx < m["x"] + m["w"]:
            mon_info = m
            mon_name = mname
            break

    metadata = {
        "monitor": mon_name,
        "origin_x": mon_info["x"],
        "origin_y": mon_info["y"],
        "width": mon_info["w"],
        "height": mon_info["h"],
        "scale": mon_info["scale"],
    }
    return jpeg_bytes, metadata
