from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import vdf

from bazzite_mcp.runner import ToolError


def _find_steam_root() -> str | None:
    candidates = [
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
        Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam",
    ]
    for path in candidates:
        if path.is_dir() and (path / "config").is_dir():
            return str(path)
    return None


def _read_vdf_file(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        parsed = vdf.load(handle)
    return parsed if isinstance(parsed, dict) else {}


def _list_acf_files(steamapps_dir: str) -> list[str]:
    try:
        return sorted(
            [
                name
                for name in os.listdir(steamapps_dir)
                if name.startswith("appmanifest_") and name.endswith(".acf")
            ]
        )
    except OSError:
        return []


def _steam_library(name_filter: str | None = None) -> str:
    """List installed Steam games with app ID and install size."""
    root = _find_steam_root()
    if not root:
        return (
            "Steam not found. Checked ~/.steam/steam, ~/.local/share/Steam, "
            "and Flatpak Steam paths."
        )

    lib_vdf_path = os.path.join(root, "config", "libraryfolders.vdf")
    try:
        lib_data = _read_vdf_file(lib_vdf_path)
    except FileNotFoundError:
        return f"Steam library config not found at {lib_vdf_path}"
    except Exception as exc:
        raise ToolError(f"Failed to parse libraryfolders.vdf: {exc}") from exc

    folders = lib_data.get("libraryfolders", lib_data.get("LibraryFolders", {}))
    library_paths: list[str] = []
    if isinstance(folders, dict):
        for value in folders.values():
            if isinstance(value, dict) and value.get("path"):
                library_paths.append(str(value["path"]))

    if not library_paths:
        return "No Steam library folders found."

    normalized_filter = name_filter.lower() if name_filter else None
    games: list[dict[str, str]] = []
    for library in library_paths:
        steamapps = os.path.join(library, "steamapps")
        for manifest_name in _list_acf_files(steamapps):
            manifest_path = os.path.join(steamapps, manifest_name)
            try:
                data = _read_vdf_file(manifest_path)
            except Exception:
                continue

            app_state = data.get("AppState", {})
            if not isinstance(app_state, dict):
                continue

            name = str(app_state.get("name", "Unknown"))
            app_id = str(app_state.get("appid", "?"))
            size_raw = app_state.get("SizeOnDisk", 0)
            try:
                size_bytes = int(str(size_raw))
            except ValueError:
                size_bytes = 0
            size_gb = (
                f"{size_bytes / (1024**3):.1f} GB" if size_bytes > 0 else "unknown"
            )

            if normalized_filter and normalized_filter not in name.lower():
                continue

            games.append(
                {
                    "app_id": app_id,
                    "name": name,
                    "size": size_gb,
                    "library": library,
                }
            )

    if not games:
        if name_filter:
            return f"No games found matching '{name_filter}'."
        return "No games installed in Steam."

    games.sort(key=lambda item: item["name"].lower())
    lines = [
        f"**{game['name']}** (ID: {game['app_id']}, {game['size']})" for game in games
    ]
    return f"Steam Library - {len(games)} games:\n\n" + "\n".join(lines)
