from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from bazzite_mcp.tools.gaming import game_reports, game_settings, steam_library


LIBRARY_FOLDERS_VDF = """"libraryfolders"
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
"""

APP_MANIFEST_ACF = """"AppState"
{
\t"appid"\t\t"1091500"
\t"name"\t\t"Cyberpunk 2077"
\t"StateFlags"\t\t"4"
\t"installdir"\t\t"Cyberpunk 2077"
\t"SizeOnDisk"\t\t"73400000000"
}
"""

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


@patch("bazzite_mcp.tools.gaming._find_steam_root")
@patch("bazzite_mcp.tools.gaming._read_vdf_file")
@patch("bazzite_mcp.tools.gaming._list_acf_files")
def test_steam_library_lists_games(mock_list_acf, mock_read_vdf, mock_root) -> None:
    import vdf

    mock_root.return_value = "/home/user/.local/share/Steam"
    mock_read_vdf.side_effect = [
        vdf.loads(LIBRARY_FOLDERS_VDF),
        vdf.loads(APP_MANIFEST_ACF),
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


@patch("bazzite_mcp.tools.gaming._fetch_protondb_summary", new_callable=AsyncMock)
@patch("bazzite_mcp.tools.gaming._fetch_protondb_reports", new_callable=AsyncMock)
@patch("bazzite_mcp.tools.gaming._get_cached_reports")
@patch("bazzite_mcp.tools.gaming._cache_reports")
def test_game_reports_fetches_and_formats(
    mock_cache_store, mock_cache_get, mock_fetch_reports, mock_fetch_summary
) -> None:
    mock_cache_get.return_value = None
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


@patch("bazzite_mcp.tools.gaming._read_mangohud_config")
@patch("bazzite_mcp.tools.gaming._read_steam_launch_options")
def test_game_settings_get(mock_read_launch_options, mock_read) -> None:
    mock_read.return_value = {"fps_limit": "60", "gpu_stats": "1"}
    mock_read_launch_options.return_value = "gamescope -- %command%"

    result = game_settings(action="get", app_id=1091500)
    assert "fps_limit" in result
    assert "60" in result
    assert "gamescope" in result


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
def test_game_settings_set_launch_options(mock_write) -> None:
    result = game_settings(
        action="set",
        app_id=1091500,
        launch_options="gamescope -w 1920 -h 1080 -F fsr -- mangohud %command%",
    )
    assert "launch options" in result.lower()
    mock_write.assert_called_once()
