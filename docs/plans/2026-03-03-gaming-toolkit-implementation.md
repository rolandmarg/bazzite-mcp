# Gaming Toolkit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 3 gaming tools (steam_library, game_reports, game_settings) that give AI agents structured local + community data to optimize games per hardware.

**Architecture:** New `tools/gaming.py` module with pure-function tools following existing patterns. VDF parsing via `vdf` library. Community data cached in `docs_cache.db` via new `game_reports` table. Config mutations audited with backup-before-write.

**Tech Stack:** Python 3.11+, `vdf` library (Valve KeyValues parser), `httpx` (existing), SQLite (existing `docs_cache.db`)

---

### Task 1: Add `vdf` dependency

**Files:**
- Modify: `pyproject.toml:10-14`

**Step 1: Add vdf to dependencies**

In `pyproject.toml`, add `vdf` to the dependencies list:

```toml
dependencies = [
    "beautifulsoup4>=4.14.3",
    "fastmcp>=3.1.0",
    "httpx>=0.28.1",
    "vdf>=3.4",
]
```

**Step 2: Install and verify**

Run: `cd /var/home/kira/bazzite-mcp && uv sync`
Expected: Dependencies install successfully, vdf available

**Step 3: Verify import works**

Run: `cd /var/home/kira/bazzite-mcp && uv run python -c "import vdf; print(vdf.__version__)"`
Expected: Prints version number (3.4+)

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add vdf library for Steam file parsing"
```

---

### Task 2: Add `game_reports` table to DB schema

**Files:**
- Modify: `src/bazzite_mcp/db.py:36-73`
- Test: `tests/test_db.py`

**Step 1: Write the failing test**

Add to `tests/test_db.py`:

```python
def test_ensure_cache_tables_includes_game_reports(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("cache.db")
    conn = get_connection(db_path)
    ensure_tables(conn, "cache")
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='game_reports'"
    )
    assert cursor.fetchone() is not None
    conn.close()
```

**Step 2: Run test to verify it fails**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_db.py::test_ensure_cache_tables_includes_game_reports -v`
Expected: FAIL — table `game_reports` does not exist

**Step 3: Add game_reports table to CACHE_SCHEMA**

In `src/bazzite_mcp/db.py`, append to `CACHE_SCHEMA` string (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS game_reports (
    app_id INTEGER PRIMARY KEY,
    protondb_summary TEXT,
    protondb_reports TEXT,
    pcgamingwiki_data TEXT,
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
```

**Step 4: Run test to verify it passes**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_db.py -v`
Expected: All pass including new test

**Step 5: Commit**

```bash
git add src/bazzite_mcp/db.py tests/test_db.py
git commit -m "feat: add game_reports table to cache schema"
```

---

### Task 3: Implement `steam_library` tool

**Files:**
- Create: `src/bazzite_mcp/tools/gaming.py`
- Test: `tests/test_tools_gaming.py`

**Step 1: Write the failing tests**

Create `tests/test_tools_gaming.py`:

```python
from __future__ import annotations

from unittest.mock import patch, mock_open

from bazzite_mcp.tools.gaming import steam_library


# Minimal VDF content for libraryfolders.vdf
LIBRARY_FOLDERS_VDF = '''"libraryfolders"
{
\t"0"
\t{
\t\t"path"\t\t"/home/user/.local/share/Steam"
\t\t"apps"
\t\t{
\t\t\t"1091500"\t\t"73400000000"
\t\t}
\t}
}
'''

# Minimal ACF content for appmanifest
APP_MANIFEST_ACF = '''"AppState"
{
\t"appid"\t\t"1091500"
\t"name"\t\t"Cyberpunk 2077"
\t"StateFlags"\t\t"4"
\t"installdir"\t\t"Cyberpunk 2077"
\t"SizeOnDisk"\t\t"73400000000"
}
'''


@patch("bazzite_mcp.tools.gaming._find_steam_root")
@patch("bazzite_mcp.tools.gaming._read_vdf_file")
@patch("bazzite_mcp.tools.gaming._list_acf_files")
def test_steam_library_lists_games(mock_list_acf, mock_read_vdf, mock_root) -> None:
    import vdf

    mock_root.return_value = "/home/user/.local/share/Steam"
    mock_read_vdf.side_effect = [
        vdf.loads(LIBRARY_FOLDERS_VDF),  # libraryfolders.vdf
        vdf.loads(APP_MANIFEST_ACF),     # appmanifest
    ]
    mock_list_acf.return_value = ["appmanifest_1091500.acf"]

    result = steam_library()
    assert "Cyberpunk 2077" in result
    assert "1091500" in result


@patch("bazzite_mcp.tools.gaming._find_steam_root")
@patch("bazzite_mcp.tools.gaming._read_vdf_file")
@patch("bazzite_mcp.tools.gaming._list_acf_files")
def test_steam_library_filter(mock_list_acf, mock_read_vdf, mock_root) -> None:
    import vdf

    mock_root.return_value = "/home/user/.local/share/Steam"
    mock_read_vdf.side_effect = [
        vdf.loads(LIBRARY_FOLDERS_VDF),
        vdf.loads(APP_MANIFEST_ACF),
    ]
    mock_list_acf.return_value = ["appmanifest_1091500.acf"]

    result = steam_library(filter="cyber")
    assert "Cyberpunk 2077" in result

    # Reset mocks for miss case
    mock_read_vdf.side_effect = [
        vdf.loads(LIBRARY_FOLDERS_VDF),
        vdf.loads(APP_MANIFEST_ACF),
    ]
    mock_list_acf.return_value = ["appmanifest_1091500.acf"]

    result = steam_library(filter="halflife")
    assert "No games found" in result or "0 games" in result.lower()


@patch("bazzite_mcp.tools.gaming._find_steam_root")
def test_steam_library_no_steam(mock_root) -> None:
    mock_root.return_value = None

    result = steam_library()
    assert "not found" in result.lower() or "not installed" in result.lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_tools_gaming.py -v`
Expected: FAIL — `bazzite_mcp.tools.gaming` does not exist

**Step 3: Implement steam_library**

Create `src/bazzite_mcp/tools/gaming.py`:

```python
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import vdf
from mcp.server.fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)


# --- Steam file helpers ---

def _find_steam_root() -> str | None:
    """Find the Steam installation root directory."""
    candidates = [
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
        Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam",
    ]
    for path in candidates:
        if path.is_dir() and (path / "config").is_dir():
            return str(path)
    return None


def _read_vdf_file(path: str) -> dict:
    """Read and parse a Valve VDF file."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return vdf.load(f)


def _list_acf_files(steamapps_dir: str) -> list[str]:
    """List appmanifest ACF files in a steamapps directory."""
    try:
        return [f for f in os.listdir(steamapps_dir) if f.startswith("appmanifest_") and f.endswith(".acf")]
    except OSError:
        return []


def steam_library(filter: str | None = None) -> str:
    """List installed Steam games with app ID, name, and install size.

    Parses Steam library folders and app manifests directly.
    Optional filter for name substring matching (case-insensitive).
    """
    root = _find_steam_root()
    if not root:
        return "Steam not found. Checked ~/.steam/steam, ~/.local/share/Steam, and Flatpak Steam paths."

    # Find all library folders
    lib_vdf_path = os.path.join(root, "config", "libraryfolders.vdf")
    if not os.path.exists(lib_vdf_path):
        return f"Steam library config not found at {lib_vdf_path}"

    try:
        lib_data = _read_vdf_file(lib_vdf_path)
    except Exception as exc:
        raise ToolError(f"Failed to parse libraryfolders.vdf: {exc}") from exc

    folders = lib_data.get("libraryfolders", lib_data.get("LibraryFolders", {}))
    library_paths: list[str] = []
    for key, value in folders.items():
        if isinstance(value, dict) and "path" in value:
            library_paths.append(value["path"])

    if not library_paths:
        return "No Steam library folders found."

    # Parse all app manifests
    games: list[dict[str, str]] = []
    for lib_path in library_paths:
        steamapps = os.path.join(lib_path, "steamapps")
        for acf_file in _list_acf_files(steamapps):
            acf_path = os.path.join(steamapps, acf_file)
            try:
                data = _read_vdf_file(acf_path)
            except Exception:
                continue

            app_state = data.get("AppState", {})
            name = app_state.get("name", "Unknown")
            app_id = app_state.get("appid", "?")
            size_bytes = int(app_state.get("SizeOnDisk", 0))
            size_gb = f"{size_bytes / (1024**3):.1f} GB" if size_bytes > 0 else "unknown"

            if filter and filter.lower() not in name.lower():
                continue

            games.append({
                "app_id": app_id,
                "name": name,
                "size": size_gb,
                "library": lib_path,
            })

    if not games:
        if filter:
            return f"No games found matching '{filter}'."
        return "No games installed in Steam."

    games.sort(key=lambda g: g["name"].lower())
    lines = [f"**{g['name']}** (ID: {g['app_id']}, {g['size']})" for g in games]
    return f"Steam Library — {len(games)} games:\n\n" + "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_tools_gaming.py -v`
Expected: All 3 tests pass

**Step 5: Run full test suite**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/bazzite_mcp/tools/gaming.py tests/test_tools_gaming.py
git commit -m "feat: add steam_library tool — parses VDF/ACF for installed games"
```

---

### Task 4: Implement `game_reports` tool

**Files:**
- Modify: `src/bazzite_mcp/tools/gaming.py`
- Modify: `src/bazzite_mcp/cache/docs_cache.py`
- Test: `tests/test_tools_gaming.py`

**Step 1: Write the failing tests**

Add to `tests/test_tools_gaming.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bazzite_mcp.tools.gaming import game_reports


PROTONDB_SUMMARY = {
    "tier": "gold",
    "score": 0.72,
    "confidence": "strong",
    "trendingTier": "gold",
    "bestReportedTier": "platinum",
    "provisionalTier": "gold",
}

PROTONDB_REPORTS = [
    {
        "rating": "gold",
        "protonVersion": "GE-Proton9-20",
        "os": "Bazzite",
        "gpu": "NVIDIA RTX 3060 Ti",
        "notes": "Works great with GE-Proton. Use gamescope -F fsr for best results.",
    },
    {
        "rating": "silver",
        "protonVersion": "Proton 9.0-4",
        "os": "Fedora",
        "gpu": "AMD RX 7800 XT",
        "notes": "Minor stuttering in cutscenes.",
    },
]


@patch("bazzite_mcp.tools.gaming._fetch_protondb_summary")
@patch("bazzite_mcp.tools.gaming._fetch_protondb_reports")
@patch("bazzite_mcp.tools.gaming._get_cached_reports")
@patch("bazzite_mcp.tools.gaming._cache_reports")
def test_game_reports_fetches_and_formats(
    mock_cache_store, mock_cache_get, mock_fetch_reports, mock_fetch_summary
) -> None:
    mock_cache_get.return_value = None  # cache miss
    mock_fetch_summary.return_value = PROTONDB_SUMMARY
    mock_fetch_reports.return_value = PROTONDB_REPORTS

    result = asyncio.run(game_reports(app_id=1091500))
    assert "gold" in result.lower()
    assert "GE-Proton" in result
    assert "RTX 3060" in result
    mock_cache_store.assert_called_once()


@patch("bazzite_mcp.tools.gaming._get_cached_reports")
def test_game_reports_uses_cache(mock_cache_get) -> None:
    mock_cache_get.return_value = {
        "protondb_summary": PROTONDB_SUMMARY,
        "protondb_reports": PROTONDB_REPORTS,
    }

    result = asyncio.run(game_reports(app_id=1091500))
    assert "gold" in result.lower()
    assert "cached" in result.lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_tools_gaming.py::test_game_reports_fetches_and_formats tests/test_tools_gaming.py::test_game_reports_uses_cache -v`
Expected: FAIL — functions don't exist yet

**Step 3: Implement cache helpers + game_reports**

Add to `src/bazzite_mcp/tools/gaming.py`:

```python
import time

import httpx

from bazzite_mcp.db import ensure_tables, get_connection, get_db_path

REPORT_CACHE_TTL = 86400  # 24 hours


# --- Cache helpers ---

def _get_cache_conn():
    db_path = get_db_path("docs_cache.db")
    conn = get_connection(db_path)
    ensure_tables(conn, "cache")
    return conn


def _get_cached_reports(app_id: int) -> dict | None:
    conn = _get_cache_conn()
    try:
        row = conn.execute(
            "SELECT protondb_summary, protondb_reports, pcgamingwiki_data, fetched_at FROM game_reports WHERE app_id = ?",
            (app_id,),
        ).fetchone()
        if not row:
            return None
        from datetime import datetime, timezone
        fetched_raw = str(row["fetched_at"])
        if fetched_raw.endswith("Z"):
            fetched_raw = fetched_raw.replace("Z", "+00:00")
        fetched = datetime.fromisoformat(fetched_raw)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - fetched).total_seconds()
        if age > REPORT_CACHE_TTL:
            return None
        return {
            "protondb_summary": json.loads(row["protondb_summary"]) if row["protondb_summary"] else None,
            "protondb_reports": json.loads(row["protondb_reports"]) if row["protondb_reports"] else None,
            "pcgamingwiki_data": json.loads(row["pcgamingwiki_data"]) if row["pcgamingwiki_data"] else None,
        }
    finally:
        conn.close()


def _cache_reports(app_id: int, summary: dict | None, reports: list | None, pcgw: dict | None = None) -> None:
    conn = _get_cache_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO game_reports (app_id, protondb_summary, protondb_reports, pcgamingwiki_data) VALUES (?, ?, ?, ?)",
            (
                app_id,
                json.dumps(summary) if summary else None,
                json.dumps(reports) if reports else None,
                json.dumps(pcgw) if pcgw else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# --- Network fetchers ---

async def _fetch_protondb_summary(app_id: int) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://www.protondb.com/api/v1/reports/summaries/{app_id}.json")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("ProtonDB summary fetch failed for %s: %s", app_id, exc)
        return None


async def _fetch_protondb_reports(app_id: int) -> list | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.protondb.com/api/v1/reports/summaries/{app_id}.json".replace(
                    "summaries", "reports"
                ).replace("{app_id}", str(app_id))
            )
            resp.raise_for_status()
            data = resp.json()
            # Return top 10 most recent reports
            if isinstance(data, list):
                return data[:10]
            return data.get("reports", data.get("results", []))[:10]
    except Exception as exc:
        logger.warning("ProtonDB reports fetch failed for %s: %s", app_id, exc)
        return None


async def game_reports(app_id: int) -> str:
    """Fetch community compatibility and optimization data for a Steam game.

    Queries ProtonDB for compatibility tier and user reports with settings recommendations.
    Results are cached for 24 hours.
    """
    # Check cache first
    cached = _get_cached_reports(app_id)
    if cached:
        return _format_reports(app_id, cached["protondb_summary"], cached["protondb_reports"], from_cache=True)

    # Fetch fresh data
    summary = await _fetch_protondb_summary(app_id)
    reports = await _fetch_protondb_reports(app_id)

    if not summary and not reports:
        return f"No ProtonDB data found for app ID {app_id}. The game may not have Linux compatibility reports yet."

    _cache_reports(app_id, summary, reports)
    return _format_reports(app_id, summary, reports, from_cache=False)


def _format_reports(app_id: int, summary: dict | None, reports: list | None, from_cache: bool = False) -> str:
    parts: list[str] = []
    cache_note = " (cached)" if from_cache else ""

    if summary:
        tier = summary.get("tier", "unknown")
        confidence = summary.get("confidence", "unknown")
        best = summary.get("bestReportedTier", "unknown")
        parts.append(
            f"## ProtonDB — App {app_id}{cache_note}\n"
            f"**Rating:** {tier.upper()}\n"
            f"**Confidence:** {confidence}\n"
            f"**Best reported:** {best}"
        )

    if reports:
        parts.append("### User Reports (most recent)")
        for report in reports[:5]:
            rating = report.get("rating", "?")
            proton = report.get("protonVersion", "?")
            gpu = report.get("gpu", "?")
            os_name = report.get("os", "?")
            notes = report.get("notes", "No notes")
            parts.append(
                f"- **{rating}** | Proton: {proton} | GPU: {gpu} | OS: {os_name}\n"
                f"  {notes}"
            )

    return "\n\n".join(parts) if parts else f"No data available for app {app_id}."
```

**Step 4: Run tests to verify they pass**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_tools_gaming.py -v`
Expected: All 5 tests pass

**Step 5: Commit**

```bash
git add src/bazzite_mcp/tools/gaming.py tests/test_tools_gaming.py
git commit -m "feat: add game_reports tool — ProtonDB community data with caching"
```

---

### Task 5: Implement `game_settings` tool

**Files:**
- Modify: `src/bazzite_mcp/tools/gaming.py`
- Test: `tests/test_tools_gaming.py`

**Step 1: Write the failing tests**

Add to `tests/test_tools_gaming.py`:

```python
from bazzite_mcp.tools.gaming import game_settings


@patch("bazzite_mcp.tools.gaming._read_mangohud_config")
def test_game_settings_get(mock_read) -> None:
    mock_read.return_value = {"fps_limit": "60", "gpu_stats": "1"}

    result = game_settings(action="get", app_id=1091500)
    assert "fps_limit" in result
    assert "60" in result


@patch("bazzite_mcp.tools.gaming._write_mangohud_config")
@patch("bazzite_mcp.tools.gaming._read_mangohud_config")
@patch("bazzite_mcp.tools.gaming._backup_file")
def test_game_settings_set_mangohud(mock_backup, mock_read, mock_write) -> None:
    mock_read.return_value = {}

    result = game_settings(
        action="set",
        app_id=1091500,
        mangohud={"fps_limit": "60", "gpu_stats": "1"},
    )
    assert "fps_limit" in result
    mock_write.assert_called_once()
    mock_backup.assert_called()


@patch("bazzite_mcp.tools.gaming._write_steam_launch_options")
@patch("bazzite_mcp.tools.gaming._backup_file")
def test_game_settings_set_launch_options(mock_backup, mock_write) -> None:
    result = game_settings(
        action="set",
        app_id=1091500,
        launch_options="gamescope -w 1920 -h 1080 -F fsr -- mangohud %command%",
    )
    assert "launch options" in result.lower()
    mock_write.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_tools_gaming.py::test_game_settings_get tests/test_tools_gaming.py::test_game_settings_set_mangohud tests/test_tools_gaming.py::test_game_settings_set_launch_options -v`
Expected: FAIL — functions don't exist

**Step 3: Implement game_settings**

Add to `src/bazzite_mcp/tools/gaming.py`:

```python
import shutil
from datetime import datetime, timezone
from typing import Literal

from bazzite_mcp.audit import AuditLog


MANGOHUD_CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.join(str(Path.home()), ".config")),
    "MangoHud",
)


def _mangohud_config_path(app_id: int | None = None) -> str:
    if app_id:
        return os.path.join(MANGOHUD_CONFIG_DIR, f"{app_id}.conf")
    return os.path.join(MANGOHUD_CONFIG_DIR, "MangoHud.conf")


def _read_mangohud_config(path: str) -> dict[str, str]:
    """Parse a MangoHud config file into key=value dict."""
    config: dict[str, str] = {}
    if not os.path.exists(path):
        return config
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()
            else:
                # Boolean flags like "no_display"
                config[line] = ""
    return config


def _write_mangohud_config(path: str, config: dict[str, str]) -> None:
    """Write a MangoHud config dict to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for key, value in config.items():
            if value:
                f.write(f"{key}={value}\n")
            else:
                f.write(f"{key}\n")


def _backup_file(path: str) -> str | None:
    """Create a timestamped backup of a file. Returns backup path."""
    if not os.path.exists(path):
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = f"{path}.bak.{ts}"
    shutil.copy2(path, backup)
    return backup


def _find_steam_userdata_dir() -> str | None:
    """Find the first Steam userdata directory (for localconfig.vdf)."""
    root = _find_steam_root()
    if not root:
        return None
    userdata = os.path.join(root, "userdata")
    if not os.path.isdir(userdata):
        return None
    for entry in os.listdir(userdata):
        config_path = os.path.join(userdata, entry, "config", "localconfig.vdf")
        if os.path.exists(config_path):
            return os.path.join(userdata, entry)
    return None


def _write_steam_launch_options(app_id: int, options: str) -> str:
    """Write launch options to Steam's localconfig.vdf."""
    user_dir = _find_steam_userdata_dir()
    if not user_dir:
        raise ToolError("Steam userdata directory not found. Is Steam installed?")

    config_path = os.path.join(user_dir, "config", "localconfig.vdf")
    _backup_file(config_path)

    data = _read_vdf_file(config_path)

    # Navigate to the launch options path
    # Path: UserLocalConfigStore > Software > Valve > Steam > apps > <appid> > LaunchOptions
    apps = (
        data.setdefault("UserLocalConfigStore", {})
        .setdefault("Software", {})
        .setdefault("Valve", {})
        .setdefault("Steam", {})
        .setdefault("apps", {})
    )
    app_entry = apps.setdefault(str(app_id), {})
    app_entry["LaunchOptions"] = options

    with open(config_path, "w", encoding="utf-8") as f:
        vdf.dump(data, f, pretty=True)

    return config_path


def game_settings(
    action: Literal["get", "set"],
    app_id: int,
    mangohud: dict[str, str] | None = None,
    launch_options: str | None = None,
) -> str:
    """Read or write per-game settings (MangoHud config and Steam launch options).

    action='get': Returns current MangoHud config and launch options for this game.
    action='set': Writes MangoHud config and/or launch options. Creates backups before writing.
    """
    if action == "get":
        mh_path = _mangohud_config_path(app_id)
        mh_global = _mangohud_config_path()
        config = _read_mangohud_config(mh_global)
        config.update(_read_mangohud_config(mh_path))

        parts = [f"## Game Settings — App {app_id}"]
        if config:
            parts.append("### MangoHud Config")
            for k, v in config.items():
                parts.append(f"  {k}={v}" if v else f"  {k}")
        else:
            parts.append("No MangoHud config found (global or per-game).")

        return "\n".join(parts)

    # action == "set"
    if not mangohud and not launch_options:
        raise ToolError("set action requires at least one of: mangohud, launch_options")

    parts = [f"## Applied Settings — App {app_id}"]

    if mangohud:
        mh_path = _mangohud_config_path(app_id)
        backup = _backup_file(mh_path)
        existing = _read_mangohud_config(mh_path)
        existing.update(mangohud)
        _write_mangohud_config(mh_path, existing)

        # Audit the change
        try:
            log = AuditLog()
            log.record(
                tool="game_settings",
                command=f"write MangoHud config {mh_path}",
                args=json.dumps({"app_id": app_id, "mangohud": mangohud}),
                result="success",
                rollback=f"cp {backup} {mh_path}" if backup else f"rm {mh_path}",
            )
        except Exception as exc:
            logger.error("Audit failed for game_settings: %s", exc)

        parts.append("### MangoHud")
        for k, v in mangohud.items():
            parts.append(f"  {k}={v}" if v else f"  {k}")
        parts.append(f"  Config: {mh_path}")
        if backup:
            parts.append(f"  Backup: {backup}")

    if launch_options:
        config_path = _write_steam_launch_options(app_id, launch_options)

        try:
            log = AuditLog()
            log.record(
                tool="game_settings",
                command=f"write Steam launch options for {app_id}",
                args=json.dumps({"app_id": app_id, "launch_options": launch_options}),
                result="success",
            )
        except Exception as exc:
            logger.error("Audit failed for game_settings: %s", exc)

        parts.append(f"### Steam launch options\n  `{launch_options}`")
        parts.append(f"  Config: {config_path}")
        parts.append("\n**Note:** Restart Steam for launch option changes to take effect.")

    return "\n".join(parts)
```

**Step 4: Run tests to verify they pass**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_tools_gaming.py -v`
Expected: All 8 tests pass

**Step 5: Commit**

```bash
git add src/bazzite_mcp/tools/gaming.py tests/test_tools_gaming.py
git commit -m "feat: add game_settings tool — MangoHud + Steam launch options with audit"
```

---

### Task 6: Register tools in server.py + add guardrail

**Files:**
- Modify: `src/bazzite_mcp/server.py`
- Modify: `src/bazzite_mcp/guardrails.py:20-63`
- Test: `tests/test_tool_registration.py`
- Test: `tests/test_guardrails.py`

**Step 1: Write failing tests**

Add to `tests/test_guardrails.py`:

```python
def test_allows_vulkaninfo() -> None:
    result = check_command("vulkaninfo --summary")
    assert result.allowed is True
```

**Step 2: Run to verify it fails**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest tests/test_guardrails.py::test_allows_vulkaninfo -v`
Expected: FAIL — `vulkaninfo` not in allowlist

**Step 3: Add vulkaninfo to guardrails allowlist**

In `src/bazzite_mcp/guardrails.py`, add `"vulkaninfo"` to `ALLOWED_COMMAND_PREFIXES` (alphabetical order, after `"ujust"`).

**Step 4: Register gaming tools in server.py**

Add imports and registration to `src/bazzite_mcp/server.py`:

```python
# Add to imports
from bazzite_mcp.tools.gaming import (
    game_reports,
    game_settings,
    steam_library,
)

# Add after audit section (line ~132)
# Gaming
mcp.tool(steam_library)
mcp.tool(game_reports)
mcp.tool(game_settings)
```

**Step 5: Run all tests**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/bazzite_mcp/server.py src/bazzite_mcp/guardrails.py tests/test_guardrails.py
git commit -m "feat: register gaming tools and add vulkaninfo to guardrail allowlist"
```

---

### Task 7: Add gaming prompt template

**Files:**
- Modify: `src/bazzite_mcp/server.py`

**Step 1: Add optimize_game prompt**

Add after the existing prompt definitions in `server.py`:

```python
@mcp.prompt()
def optimize_game(game_name: str) -> str:
    """Optimize a game's settings based on hardware and community data."""
    return (
        f"Optimize '{game_name}' for this system:\n\n"
        "1. Run steam_library to find the game and get its app ID\n"
        "2. Run hardware_info to get GPU, CPU, and RAM details\n"
        "3. Run game_reports with the app ID to get ProtonDB community data\n"
        "4. Based on hardware + community reports, determine:\n"
        "   - Best Proton version to use\n"
        "   - Gamescope launch flags (resolution, scaler, FPS limit)\n"
        "   - MangoHud monitoring settings\n"
        "   - Whether to enable GameMode\n"
        "5. Apply settings with game_settings tool\n"
        "6. Enable GameMode if recommended: manage_service(service='gamemoded', action='enable', user=True)\n\n"
        "Explain each recommendation and why it suits this hardware."
    )
```

**Step 2: Run tests**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest -v`
Expected: All pass

**Step 3: Commit**

```bash
git add src/bazzite_mcp/server.py
git commit -m "feat: add optimize_game prompt template for gaming workflow"
```

---

### Task 8: Update server instructions

**Files:**
- Modify: `src/bazzite_mcp/server.py:63-73`

**Step 1: Add gaming guidance to server instructions**

Update the `instructions` parameter of `FastMCP()` to include gaming:

```python
mcp = FastMCP(
    "bazzite",
    instructions=(
        "Bazzite OS management server. Key principles:\n"
        "1. Always check ujust first for system operations (ujust_list, ujust_show, ujust_run)\n"
        "2. Follow the 6-tier install hierarchy: ujust > flatpak > brew > distrobox > AppImage > rpm-ostree\n"
        "3. Use query_bazzite_docs to search cached documentation\n"
        "4. Every mutation is audit-logged with rollback support — check audit_log_query to review actions\n"
        "5. For containers: prefer distrobox for dev environments, quadlet for persistent services\n"
        "6. rpm-ostree install is a LAST RESORT — it can freeze updates and block rebasing\n"
        "7. For gaming: use steam_library to find games, game_reports for community optimization data, "
        "game_settings to apply MangoHud/launch options. Use hardware_info + game_reports to make "
        "hardware-aware recommendations. Existing manage_service covers GameMode."
    ),
)
```

**Step 2: Run tests**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest -v`
Expected: All pass

**Step 3: Commit**

```bash
git add src/bazzite_mcp/server.py
git commit -m "feat: update server instructions with gaming workflow guidance"
```

---

### Task 9: Final integration test — run the server

**Step 1: Verify server starts cleanly**

Run: `cd /var/home/kira/bazzite-mcp && timeout 5 uv run python -m bazzite_mcp 2>&1; echo "Exit: $?"`
Expected: Server starts (may timeout after 5s waiting for stdio, exit 124 is fine)

**Step 2: Run full test suite one final time**

Run: `cd /var/home/kira/bazzite-mcp && uv run pytest -v`
Expected: All tests pass

**Step 3: Verify tool count**

Run: `cd /var/home/kira/bazzite-mcp && uv run python -c "from bazzite_mcp.server import mcp; print(f'Tools: {len(mcp._tool_manager._tools)}')" 2>/dev/null`
Expected: Tools: 45 (42 existing + 3 new)
