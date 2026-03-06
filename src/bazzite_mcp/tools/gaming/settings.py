from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import vdf

from bazzite_mcp.audit import AuditLog
from bazzite_mcp.runner import ToolError
from .library import _find_steam_root, _read_vdf_file

logger = logging.getLogger(__name__)

MANGOHUD_CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.join(str(Path.home()), ".config")),
    "MangoHud",
)


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
            logger.error("Audit failed for gaming launch options update: %s", exc)

        parts.append(f"### Steam launch options\n  `{launch_options}`")
        parts.append(f"  Config: {config_path}")
        parts.append("  Note: restart Steam for launch option changes to take effect.")

    return "\n".join(parts)
