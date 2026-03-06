from __future__ import annotations

from pathlib import Path

from bazzite_mcp.portal import PortalClient, get_portal

SCREENSHOT_DIR = Path("/tmp/bazzite-mcp")
YDOTOOL_SOCKET = SCREENSHOT_DIR / "ydotool.sock"


def _get_portal() -> PortalClient:
    """Get portal client (lazy, may not be connected)."""
    return get_portal()
