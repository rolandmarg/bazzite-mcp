from __future__ import annotations

import time
from typing import Literal

from fastmcp.utilities.types import Image
from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.desktop_env import format_graphical_error
from bazzite_mcp.runner import run_command
from .shared import SCREENSHOT_DIR
from .windows import _kwin_activate, _resolve_window


def screenshot(
    target: Literal["desktop", "window"] = "window",
    window: str | None = None,
):
    """Capture the desktop or active window as an image file."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    png_path = SCREENSHOT_DIR / f"screenshot-{target}-{timestamp}.png"

    if target == "window":
        if window:
            uuid = _resolve_window(window)
            _kwin_activate(uuid)
            time.sleep(0.4)

        result = run_command(f"spectacle -b -n -a -o {png_path}")
        if result.returncode != 0:
            raise ToolError(format_graphical_error("Spectacle capture failed", result.stderr))
        return [Image(path=str(png_path)), "Captured active window"]

    result = run_command(f"spectacle -b -n -f -o {png_path}")
    if result.returncode != 0:
        raise ToolError(format_graphical_error("Spectacle capture failed", result.stderr))
    return [Image(path=str(png_path)), "Captured desktop"]
