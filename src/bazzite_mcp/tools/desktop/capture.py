from __future__ import annotations

import json
import time
from typing import Literal

from fastmcp.utilities.types import Image
from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.kwin_screenshot import capture_screen
from bazzite_mcp.runner import run_command
from .shared import SCREENSHOT_DIR, _get_portal
from .windows import _kwin_activate, _resolve_window

_last_screenshot_meta: dict | None = None


def connect_portal() -> str:
    """Establish a portal session for input control."""
    portal = _get_portal()
    if portal.is_connected:
        return "Portal session already active."
    result = portal.connect()
    return f"Portal session established: {json.dumps(result)}"


def screenshot(
    target: Literal["desktop", "window", "monitor"] = "window",
    window: str | None = None,
    monitor: str | None = None,
):
    """Capture the desktop, a window, or a monitor as a compressed JPEG."""
    global _last_screenshot_meta

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)

    if target == "window":
        if window:
            uuid = _resolve_window(window)
            _kwin_activate(uuid)
            time.sleep(0.4)
        png_path = SCREENSHOT_DIR / f"win-{timestamp}.png"
        jpg_path = png_path.with_suffix(".jpg")
        result = run_command(
            f"spectacle -a --background --nonotify --output {png_path}"
        )
        if result.returncode != 0:
            raise ToolError(f"spectacle capture failed: {result.stderr}")
        conv = run_command(f"magick {png_path} -quality 85 {jpg_path}")
        if conv.returncode != 0:
            jpeg_bytes = png_path.read_bytes()
            img_path = png_path
        else:
            jpeg_bytes = jpg_path.read_bytes()
            png_path.unlink(missing_ok=True)
            img_path = jpg_path
        info = f"Screenshot: active window ({len(jpeg_bytes)} bytes)"
        _last_screenshot_meta = None
        return [Image(path=str(img_path)), info]

    jpeg_bytes, meta = capture_screen(monitor)
    jpg_path = SCREENSHOT_DIR / f"capture-{timestamp}.jpg"
    jpg_path.write_bytes(jpeg_bytes)
    _last_screenshot_meta = meta
    mon_name = meta.get("monitor", monitor or "unknown")
    width = meta.get("width", "?")
    height = meta.get("height", "?")
    origin_x = meta.get("origin_x", 0)
    origin_y = meta.get("origin_y", 0)
    scale = meta.get("scale", 1.0)
    info = (
        f'Screenshot: monitor "{mon_name}" ({width}x{height})\n'
        f"Coordinates: origin=({origin_x}, {origin_y}), scale={scale}\n"
        f"Use pixel coordinates from this image with send_input(mode=\"mouse\")."
    )
    return [Image(path=str(jpg_path)), info]
