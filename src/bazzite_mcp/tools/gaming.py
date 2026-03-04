from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
import vdf

from bazzite_mcp.audit import AuditLog
from bazzite_mcp.db import ensure_tables, get_connection, get_db_path
from bazzite_mcp.runner import ToolError

logger = logging.getLogger(__name__)

REPORT_CACHE_TTL = 86400
MANGOHUD_CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.join(str(Path.home()), ".config")),
    "MangoHud",
)


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


def _get_cache_conn():
    db_path = get_db_path("docs_cache.db")
    conn = get_connection(db_path)
    ensure_tables(conn, "cache")
    return conn


def _get_cached_reports(app_id: int) -> dict[str, Any] | None:
    conn = _get_cache_conn()
    try:
        row = conn.execute(
            "SELECT protondb_summary, pcgamingwiki_data, fetched_at "
            "FROM game_reports WHERE app_id = ?",
            (app_id,),
        ).fetchone()
        if not row:
            return None

        fetched_raw = str(row["fetched_at"])
        if fetched_raw.endswith("Z"):
            fetched_raw = fetched_raw.replace("Z", "+00:00")

        try:
            fetched = datetime.fromisoformat(fetched_raw)
        except ValueError:
            return None

        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - fetched).total_seconds()
        if age > REPORT_CACHE_TTL:
            return None

        return {
            "protondb_summary": (
                json.loads(row["protondb_summary"]) if row["protondb_summary"] else None
            ),
            "pcgamingwiki_data": (
                json.loads(row["pcgamingwiki_data"])
                if row["pcgamingwiki_data"]
                else None
            ),
        }
    finally:
        conn.close()


def _cache_reports(
    app_id: int,
    summary: dict[str, Any] | None,
    pcgw: dict[str, Any] | None = None,
) -> None:
    conn = _get_cache_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO game_reports "
            "(app_id, protondb_summary, pcgamingwiki_data) VALUES (?, ?, ?)",
            (
                app_id,
                json.dumps(summary) if summary else None,
                json.dumps(pcgw) if pcgw else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def _fetch_protondb_summary(app_id: int) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"https://www.protondb.com/api/v1/reports/summaries/{app_id}.json"
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("ProtonDB summary fetch failed for %s: %s", app_id, exc)
        return None


async def _fetch_pcgamingwiki_data(app_id: int) -> dict[str, Any] | None:
    try:
        params = {
            "action": "cargoquery",
            "format": "json",
            "tables": "Infobox_game,Video,Input,API,Cloud",
            "join_on": (
                "Infobox_game._pageName=Video._pageName,"
                "Infobox_game._pageName=Input._pageName,"
                "Infobox_game._pageName=API._pageName,"
                "Infobox_game._pageName=Cloud._pageName"
            ),
            "fields": (
                "Infobox_game._pageName=Page,"
                "Infobox_game.Steam_AppID,"
                "Infobox_game.Developers,"
                "Infobox_game.Publishers,"
                "Infobox_game.Released,"
                "Infobox_game.Genres,"
                "Video.Upscaling,"
                "Video.Frame_gen,"
                "Video.Vsync,"
                "Input.Controller_support,"
                "Input.Full_controller_support,"
                "API.Vulkan_versions,"
                "Cloud.Steam=Steam_cloud"
            ),
            "where": f'Infobox_game.Steam_AppID HOLDS "{app_id}"',
            "limit": "1",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://www.pcgamingwiki.com/w/api.php", params=params
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return None

            rows = payload.get("cargoquery")
            if not isinstance(rows, list) or not rows:
                return None

            first = rows[0]
            if not isinstance(first, dict):
                return None

            title = first.get("title")
            if not isinstance(title, dict):
                return None

            return {
                "page": title.get("Page"),
                "steam_app_id": title.get("Steam AppID"),
                "developers": title.get("Developers"),
                "publishers": title.get("Publishers"),
                "released": title.get("Released"),
                "genres": title.get("Genres"),
                "upscaling": title.get("Upscaling"),
                "frame_gen": title.get("Frame gen"),
                "vsync": title.get("Vsync"),
                "controller_support": title.get("Controller support"),
                "full_controller_support": title.get("Full controller support"),
                "vulkan_versions": title.get("Vulkan versions"),
                "steam_cloud": title.get("Steam_cloud"),
            }
    except Exception as exc:
        logger.warning("PCGamingWiki fetch failed for %s: %s", app_id, exc)
        return None


def _format_reports(
    app_id: int,
    summary: dict[str, Any] | None,
    pcgw: dict[str, Any] | None,
    from_cache: bool = False,
) -> str:
    parts: list[str] = []
    cache_note = " (cached)" if from_cache else ""

    if summary:
        tier = str(summary.get("tier", "unknown"))
        confidence = str(summary.get("confidence", "unknown"))
        best = str(summary.get("bestReportedTier", "unknown"))
        trending = str(summary.get("trendingTier", "unknown"))
        total = summary.get("total")
        parts.append(
            f"## ProtonDB - App {app_id}{cache_note}\n"
            f"**Rating:** {tier.upper()}\n"
            f"**Confidence:** {confidence}\n"
            f"**Trending tier:** {trending}\n"
            f"**Best reported:** {best}\n"
            f"**Total reports:** {total if total is not None else 'unknown'}"
        )

    if pcgw:
        page = pcgw.get("page") or f"App {app_id}"
        parts.append(
            f"## PCGamingWiki - {page}\n"
            f"**Upscaling:** {pcgw.get('upscaling') or 'unknown'}\n"
            f"**Frame generation:** {pcgw.get('frame_gen') or 'unknown'}\n"
            f"**VSync:** {pcgw.get('vsync') or 'unknown'}\n"
            f"**Controller support:** {pcgw.get('controller_support') or 'unknown'}\n"
            f"**Full controller support:** {pcgw.get('full_controller_support') or 'unknown'}\n"
            f"**Vulkan:** {pcgw.get('vulkan_versions') or 'not listed'}\n"
            f"**Steam Cloud:** {pcgw.get('steam_cloud') or 'unknown'}"
        )

    return "\n\n".join(parts) if parts else f"No data available for app {app_id}."


async def _game_reports(app_id: int) -> str:
    """Fetch compatibility and optimization hints for a Steam game."""
    cached = _get_cached_reports(app_id)
    if cached:
        return _format_reports(
            app_id,
            cached.get("protondb_summary"),
            cached.get("pcgamingwiki_data"),
            from_cache=True,
        )

    summary = await _fetch_protondb_summary(app_id)
    pcgw = await _fetch_pcgamingwiki_data(app_id)
    if not summary and not pcgw:
        return (
            f"No community data found for app ID {app_id}. "
            "Could not retrieve ProtonDB summary or PCGamingWiki entries."
        )

    _cache_reports(app_id, summary, pcgw)
    return _format_reports(app_id, summary, pcgw, from_cache=False)


def _mangohud_config_path(app_id: int | None = None) -> str:
    if app_id is None:
        return os.path.join(MANGOHUD_CONFIG_DIR, "MangoHud.conf")
    return os.path.join(MANGOHUD_CONFIG_DIR, f"{app_id}.conf")


def _read_mangohud_config(path: str) -> dict[str, str]:
    config: dict[str, str] = {}
    if not os.path.exists(path):
        return config

    with open(path, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, value = stripped.partition("=")
                config[key.strip()] = value.strip()
            else:
                config[stripped] = ""
    return config


def _write_mangohud_config(path: str, config: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for key, value in config.items():
            if value:
                handle.write(f"{key}={value}\n")
            else:
                handle.write(f"{key}\n")


def _backup_file(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.bak.{timestamp}"
    shutil.copy2(path, backup_path)
    return backup_path


def _find_steam_userdata_dir() -> str | None:
    root = _find_steam_root()
    if not root:
        return None

    userdata_dir = os.path.join(root, "userdata")
    if not os.path.isdir(userdata_dir):
        return None

    for entry in os.listdir(userdata_dir):
        config_path = os.path.join(userdata_dir, entry, "config", "localconfig.vdf")
        if os.path.exists(config_path):
            return os.path.join(userdata_dir, entry)
    return None


def _read_steam_launch_options(app_id: int) -> str | None:
    user_dir = _find_steam_userdata_dir()
    if not user_dir:
        return None

    config_path = os.path.join(user_dir, "config", "localconfig.vdf")
    if not os.path.exists(config_path):
        return None

    try:
        data = _read_vdf_file(config_path)
    except Exception:
        return None

    app_entry = (
        data.get("UserLocalConfigStore", {})
        .get("Software", {})
        .get("Valve", {})
        .get("Steam", {})
        .get("apps", {})
        .get(str(app_id), {})
    )
    if isinstance(app_entry, dict):
        launch_options = app_entry.get("LaunchOptions")
        return str(launch_options) if launch_options else None
    return None


def _write_steam_launch_options(app_id: int, options: str) -> str:
    user_dir = _find_steam_userdata_dir()
    if not user_dir:
        raise ToolError("Steam userdata directory not found. Is Steam installed?")

    config_path = os.path.join(user_dir, "config", "localconfig.vdf")
    _backup_file(config_path)

    data = _read_vdf_file(config_path)
    apps = (
        data.setdefault("UserLocalConfigStore", {})
        .setdefault("Software", {})
        .setdefault("Valve", {})
        .setdefault("Steam", {})
        .setdefault("apps", {})
    )
    app_entry = apps.setdefault(str(app_id), {})
    app_entry["LaunchOptions"] = options

    with open(config_path, "w", encoding="utf-8") as handle:
        vdf.dump(data, handle, pretty=True)
    return config_path


def _game_settings_get(app_id: int) -> str:
    """Read per-game settings for MangoHud and Steam launch options."""
    global_path = _mangohud_config_path()
    game_path = _mangohud_config_path(app_id)
    combined = _read_mangohud_config(global_path)
    combined.update(_read_mangohud_config(game_path))
    launch = _read_steam_launch_options(app_id)

    parts = [f"## Game Settings - App {app_id}"]
    if combined:
        parts.append("### MangoHud Config")
        for key, value in combined.items():
            parts.append(f"  {key}={value}" if value else f"  {key}")
    else:
        parts.append("No MangoHud config found (global or per-game).")

    if launch:
        parts.append(f"### Steam Launch Options\n  `{launch}`")

    return "\n".join(parts)


def _game_settings_set(
    app_id: int,
    mangohud: dict[str, str] | None = None,
    launch_options: str | None = None,
) -> str:
    """Write per-game settings for MangoHud and Steam launch options."""
    if not mangohud and not launch_options:
        raise ToolError("At least one of 'mangohud' or 'launch_options' is required.")

    parts = [f"## Applied Settings - App {app_id}"]

    if mangohud:
        game_path = _mangohud_config_path(app_id)
        backup = _backup_file(game_path)
        existing = _read_mangohud_config(game_path)
        existing.update(mangohud)
        _write_mangohud_config(game_path, existing)

        try:
            with AuditLog() as log:
                rollback = f"cp {backup} {game_path}" if backup else f"rm {game_path}"
                log.record(
                    tool="gaming",
                    command=f"write MangoHud config {game_path}",
                    args=json.dumps({"app_id": app_id, "mangohud": mangohud}),
                    result="success",
                    rollback=rollback,
                )
        except Exception as exc:
            logger.error("Audit failed for gaming MangoHud update: %s", exc)

        parts.append("### MangoHud")
        for key, value in mangohud.items():
            parts.append(f"  {key}={value}" if value else f"  {key}")
        parts.append(f"  Config: {game_path}")
        if backup:
            parts.append(f"  Backup: {backup}")

    if launch_options:
        config_path = _write_steam_launch_options(app_id, launch_options)

        try:
            with AuditLog() as log:
                log.record(
                    tool="gaming",
                    command=f"write Steam launch options for {app_id}",
                    args=json.dumps(
                        {"app_id": app_id, "launch_options": launch_options}
                    ),
                    result="success",
                )
        except Exception as exc:
            logger.error(
                "Audit failed for gaming launch options update: %s", exc
            )

        parts.append(f"### Steam launch options\n  `{launch_options}`")
        parts.append(f"  Config: {config_path}")
        parts.append("  Note: restart Steam for launch option changes to take effect.")

    return "\n".join(parts)


# --- Dispatcher ---


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
