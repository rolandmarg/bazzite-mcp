from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.runner import run_command

SCREENSHOT_DIR = Path("/tmp/bazzite-mcp")


def screenshot() -> str:
    """Capture the full desktop and return a compressed, AI-vision-ready JPEG path.

    Uses Spectacle (KDE) for capture and ImageMagick for JPEG compression.
    Falls back to raw PNG if ImageMagick is not available.
    """
    if not shutil.which("spectacle"):
        raise ToolError(
            "spectacle is not installed. "
            "It should be pre-installed on Bazzite KDE — check your image."
        )

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    png_path = SCREENSHOT_DIR / f"screenshot-{timestamp}.png"
    jpg_path = SCREENSHOT_DIR / f"screenshot-{timestamp}.jpg"

    result = run_command(
        f"spectacle --fullscreen --background --nonotify --output {png_path}"
    )
    if result.returncode != 0:
        raise ToolError(f"Spectacle capture failed: {result.stderr}")

    if not shutil.which("magick"):
        return str(png_path)

    result = run_command(
        f"magick {png_path} -resize 5120x -quality 75 {jpg_path}"
    )
    if result.returncode != 0:
        return str(png_path)

    png_path.unlink(missing_ok=True)
    return str(jpg_path)
