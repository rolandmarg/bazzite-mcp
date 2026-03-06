"""Helpers for recovering a usable graphical session environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from bazzite_mcp.config import load_config

GUI_ENV_KEYS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "XDG_SESSION_TYPE",
)

_PREFERRED_PROCESSES = (
    "plasmashell",
    "kwin_wayland",
    "kwin_x11",
    "xdg-desktop-portal-kde",
    "xdg-desktop-portal",
)


def _normalize_graphical_env(env: dict[str, str]) -> dict[str, str]:
    normalized = {key: value for key, value in env.items() if value}

    runtime_dir = normalized.get("XDG_RUNTIME_DIR")
    if runtime_dir and not normalized.get("DBUS_SESSION_BUS_ADDRESS"):
        normalized["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime_dir}/bus"

    if not normalized.get("XDG_SESSION_TYPE"):
        if normalized.get("WAYLAND_DISPLAY"):
            normalized["XDG_SESSION_TYPE"] = "wayland"
        elif normalized.get("DISPLAY"):
            normalized["XDG_SESSION_TYPE"] = "x11"

    return normalized


def _env_score(env: dict[str, str], process_name: str) -> int:
    score = 0
    if env.get("WAYLAND_DISPLAY"):
        score += 4
    if env.get("DISPLAY"):
        score += 3
    if env.get("XDG_RUNTIME_DIR"):
        score += 2
    if env.get("DBUS_SESSION_BUS_ADDRESS"):
        score += 2
    if process_name in _PREFERRED_PROCESSES:
        score += max(1, len(_PREFERRED_PROCESSES) - _PREFERRED_PROCESSES.index(process_name))
    return score


def _current_graphical_env() -> dict[str, str]:
    return _normalize_graphical_env({key: os.environ.get(key, "") for key in GUI_ENV_KEYS})


def _is_usable_graphical_env(env: dict[str, str]) -> bool:
    has_display = bool(env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"))
    has_runtime = bool(env.get("XDG_RUNTIME_DIR"))
    has_bus = bool(env.get("DBUS_SESSION_BUS_ADDRESS"))
    return has_display and has_runtime and has_bus


def _read_proc_environ(pid: int) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return {}

    env: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key_b, value_b = item.split(b"=", 1)
        key = key_b.decode("utf-8", errors="ignore")
        if key not in GUI_ENV_KEYS:
            continue
        env[key] = value_b.decode("utf-8", errors="ignore")
    return _normalize_graphical_env(env)


def _iter_candidate_processes() -> list[tuple[str, int]]:
    uid = os.getuid()
    candidates: list[tuple[str, int]] = []

    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue

        try:
            if proc_dir.stat().st_uid != uid:
                continue
            process_name = (proc_dir / "comm").read_text(encoding="utf-8").strip()
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue

        if process_name in _PREFERRED_PROCESSES:
            candidates.append((process_name, int(proc_dir.name)))

    return candidates


@lru_cache(maxsize=1)
def get_graphical_env() -> dict[str, str]:
    """Return the best-known graphical session environment.

    Returns env vars to overlay onto subprocesses. Does not mutate
    os.environ so the server stays responsive to session changes on restart.
    """
    load_config()

    current = _current_graphical_env()
    if _is_usable_graphical_env(current):
        return current

    best = current
    best_score = _env_score(current, "")

    for process_name, pid in _iter_candidate_processes():
        candidate = _read_proc_environ(pid)
        score = _env_score(candidate, process_name)
        if score > best_score:
            best = candidate
            best_score = score

    return best


def build_command_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Merge the recovered graphical environment into a subprocess env."""
    env = dict(os.environ)
    if base:
        env.update(base)
    env.update(get_graphical_env())
    return env


def format_graphical_error(prefix: str, detail: str | None = None) -> str:
    """Add a targeted hint when a desktop command lacks GUI session access."""
    message = prefix
    cleaned = (detail or "").strip()
    if cleaned:
        message = f"{message}: {cleaned}"

    lowered = cleaned.lower()
    if (
        "cannot autolaunch d-bus" in lowered
        or "unable to autolaunch a dbus-daemon" in lowered
        or ("display" in lowered and "dbus" in lowered)
    ):
        message += (
            " The MCP server is missing the active graphical session environment. "
            "Restart the MCP server from the desktop session, or set "
            "DISPLAY/WAYLAND_DISPLAY/XDG_RUNTIME_DIR/DBUS_SESSION_BUS_ADDRESS in "
            "~/.config/bazzite-mcp/env."
        )

    return message


def reset_graphical_env_cache() -> None:
    """Clear cached graphical environment state (for tests)."""
    get_graphical_env.cache_clear()
