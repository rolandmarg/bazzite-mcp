from __future__ import annotations

import json
import struct
import time
from pathlib import Path
from typing import Literal

from fastmcp.utilities.types import Image
from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.desktop_env import format_graphical_error
from bazzite_mcp.screen_geometry import get_monitor_info
from bazzite_mcp.runner import run_command
from .shared import SCREENSHOT_DIR
from .windows import _kwin_activate, _kwin_get_window_info, _kwin_query_window_info, _resolve_window


def _read_png_dimensions(path: Path) -> tuple[int, int]:
    """Read width and height from a PNG header without extra dependencies."""
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ToolError(f"Screenshot is not a valid PNG: {path}")
    return struct.unpack(">II", header[16:24])


def _build_metadata(path: Path, status: str, target: str) -> str:
    width, height = _read_png_dimensions(path)
    metadata = {
        "status": status,
        "target": target,
        "path": str(path),
        "format": "png",
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
        "origin_x": 0,
        "origin_y": 0,
        "scale": 1.0,
    }
    if target == "window":
        window_info = _kwin_query_window_info()
        if window_info:
            metadata["origin_x"] = int(window_info.get("x", 0))
            metadata["origin_y"] = int(window_info.get("y", 0))
            metadata["scale"] = _monitor_scale_for_point(
                metadata["origin_x"],
                metadata["origin_y"],
            )
    return json.dumps(metadata)


def _monitor_scale_for_point(x: int, y: int) -> float:
    monitors = get_monitor_info()
    for monitor in monitors.values():
        if (
            monitor["x"] <= x < monitor["x"] + monitor["w"]
            and monitor["y"] <= y < monitor["y"] + monitor["h"]
        ):
            return float(monitor.get("scale", 1.0))
    return 1.0


def screenshot(
    target: Literal["desktop", "window"] = "window",
    window: str | None = None,
):
    """Capture the desktop or active window as an image file."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    png_path = SCREENSHOT_DIR / f"screenshot-{target}-{timestamp}.png"

    if target == "window":
        target_window_info: dict | None = None
        if window:
            uuid = _resolve_window(window)
            target_window_info = _kwin_get_window_info(uuid)
            _kwin_activate(uuid)
            time.sleep(0.4)

        result = run_command(["spectacle", "-b", "-n", "-a", "-o", str(png_path)])
        if result.returncode != 0:
            raise ToolError(format_graphical_error("Spectacle capture failed", result.stderr))
        if target_window_info:
            return [
                Image(path=str(png_path)),
                _build_window_metadata(png_path, "Captured active window", target_window_info),
            ]
        return [Image(path=str(png_path)), _build_metadata(png_path, "Captured active window", target)]

    result = run_command(["spectacle", "-b", "-n", "-f", "-o", str(png_path)])
    if result.returncode != 0:
        raise ToolError(format_graphical_error("Spectacle capture failed", result.stderr))
    return [Image(path=str(png_path)), _build_metadata(png_path, "Captured desktop", target)]


def _build_window_metadata(path: Path, status: str, window_info: dict) -> str:
    width, height = _read_png_dimensions(path)
    origin_x = int(window_info.get("x", 0))
    origin_y = int(window_info.get("y", 0))
    return json.dumps(
        {
            "status": status,
            "target": "window",
            "path": str(path),
            "format": "png",
            "width": width,
            "height": height,
            "bytes": path.stat().st_size,
            "origin_x": origin_x,
            "origin_y": origin_y,
            "scale": _monitor_scale_for_point(origin_x, origin_y),
        }
    )
