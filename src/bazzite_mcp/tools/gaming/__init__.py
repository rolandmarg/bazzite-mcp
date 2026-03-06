from __future__ import annotations

from typing import Literal

from bazzite_mcp.runner import ToolError

from .library import _steam_library
from .reports import _game_reports
from .settings import _game_settings_get, _game_settings_set

__all__ = [
    "_game_reports",
    "_game_settings_get",
    "_game_settings_set",
    "_steam_library",
    "gaming",
]


async def gaming(
    action: Literal["library", "reports", "settings_get", "settings_set"],
    app_id: int | None = None,
    name_filter: str | None = None,
    mangohud: dict[str, str] | None = None,
    launch_options: str | None = None,
) -> str:
    """Steam library, ProtonDB/PCGamingWiki reports, and per-game settings."""
    if action == "library":
        return _steam_library(name_filter)
    if not app_id:
        raise ToolError(f"'app_id' is required for action='{action}'.")
    if action == "reports":
        return await _game_reports(app_id)
    if action == "settings_get":
        return _game_settings_get(app_id)
    if action == "settings_set":
        return _game_settings_set(app_id, mangohud, launch_options)
    raise ToolError(f"Unknown action '{action}'.")
