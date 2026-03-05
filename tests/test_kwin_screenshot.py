"""Tests for kwin_screenshot module."""

from unittest.mock import MagicMock, call, patch

import pytest

from bazzite_mcp.kwin_screenshot import (
    capture_active_window,
    get_active_window_info,
    get_monitor_info,
    get_window_scale,
)
from bazzite_mcp.runner import CommandResult

# Sample kscreen-doctor output (ANSI codes stripped for clarity -- the module
# strips them itself, but we include a couple here to verify stripping works).
KSCREEN_OUTPUT = (
    "\x1b[01;32mOutput: \x1b[0;0m1 HDMI-A-1 73ff556f-3261-405a-abc6-c92363fc4073\n"
    "\tenabled\n"
    "\tconnected\n"
    "\tpriority 2\n"
    "\tGeometry: 2560,169 2560x1440\n"
    "\tScale: 1.5\n"
    "\tRotation: 1\n"
    "\x1b[01;32mOutput: \x1b[0;0m2 HDMI-A-2 df58f18c-66b5-4d20-9c49-7a52ba92e3bc\n"
    "\tenabled\n"
    "\tconnected\n"
    "\tpriority 1\n"
    "\tGeometry: 0,0 2560x1440\n"
    "\tScale: 1\n"
    "\tRotation: 1\n"
)

QDBUS_WINDOW_OUTPUT = (
    "activities: a1719f67-6bac-49d3-a844-c76d5708424a\n"
    "caption: Hello World - Firefox\n"
    "clientMachine: \n"
    "desktopFile: org.mozilla.firefox\n"
    "fullscreen: false\n"
    "height: 900\n"
    "keepAbove: false\n"
    "minimized: false\n"
    "resourceClass: firefox\n"
    "uuid: {abcd1234-5678-9abc-def0-123456789abc}\n"
    "width: 1200\n"
    "x: 200\n"
    "y: 100\n"
)


@patch("bazzite_mcp.kwin_screenshot.run_command")
def test_get_monitor_info(mock_run: MagicMock) -> None:
    """Parses kscreen-doctor output into structured monitor dict."""
    # Clear lru_cache from prior runs
    get_monitor_info.cache_clear()

    mock_run.return_value = CommandResult(
        returncode=0, stdout=KSCREEN_OUTPUT, stderr=""
    )

    monitors = get_monitor_info()

    assert "HDMI-A-1" in monitors
    assert "HDMI-A-2" in monitors

    m1 = monitors["HDMI-A-1"]
    assert m1["x"] == 2560
    assert m1["y"] == 169
    assert m1["w"] == 2560
    assert m1["h"] == 1440
    assert m1["scale"] == 1.5

    m2 = monitors["HDMI-A-2"]
    assert m2["x"] == 0
    assert m2["y"] == 0
    assert m2["w"] == 2560
    assert m2["h"] == 1440
    assert m2["scale"] == 1.0

    # Clean up cache so it doesn't leak into other tests
    get_monitor_info.cache_clear()


@patch("bazzite_mcp.kwin_screenshot.run_command")
def test_get_active_window_info(mock_run: MagicMock) -> None:
    """Parses qdbus queryWindowInfo output into a dict."""
    mock_run.return_value = CommandResult(
        returncode=0, stdout=QDBUS_WINDOW_OUTPUT, stderr=""
    )

    info = get_active_window_info()

    assert info["uuid"] == "abcd1234-5678-9abc-def0-123456789abc"
    assert info["caption"] == "Hello World - Firefox"
    assert info["x"] == 200
    assert info["y"] == 100
    assert info["width"] == 1200
    assert info["height"] == 900


@patch("bazzite_mcp.kwin_screenshot.run_command")
def test_get_active_window_info_float_values(mock_run: MagicMock) -> None:
    """Handles fractional geometry values from KWin (truncates to int)."""
    mock_run.return_value = CommandResult(
        returncode=0,
        stdout=(
            "caption: Yakuake\n"
            "uuid: {e88f7a69-84ed-4eec-aaef-4f25bd9575be}\n"
            "width: 2304\n"
            "height: 1137.33333333333\n"
            "x: 2688\n"
            "y: 169\n"
        ),
        stderr="",
    )

    info = get_active_window_info()

    assert info["height"] == 1137
    assert info["width"] == 2304


@patch("bazzite_mcp.kwin_screenshot.run_command")
def test_get_window_scale(mock_run: MagicMock) -> None:
    """Returns correct scale based on which monitor contains window_x."""
    get_monitor_info.cache_clear()

    mock_run.return_value = CommandResult(
        returncode=0, stdout=KSCREEN_OUTPUT, stderr=""
    )

    # Window on left monitor (HDMI-A-2, x=0..2560, scale=1.0)
    assert get_window_scale(500) == 1.0
    assert get_window_scale(0) == 1.0
    assert get_window_scale(2559) == 1.0

    # Window on right monitor (HDMI-A-1, x=2560..5120, scale=1.5)
    assert get_window_scale(2560) == 1.5
    assert get_window_scale(3000) == 1.5

    # Window outside any monitor region -- defaults to 1.0
    assert get_window_scale(9999) == 1.0

    get_monitor_info.cache_clear()


@patch("bazzite_mcp.kwin_screenshot.run_command")
def test_capture_active_window(mock_run: MagicMock) -> None:
    """Calls spectacle, converts to JPEG, and returns correct metadata."""
    get_monitor_info.cache_clear()

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    fake_jpg = b"\xff\xd8\xff" + b"\x00" * 100

    def side_effect(cmd, **kwargs):
        if "queryWindowInfo" in cmd:
            return CommandResult(
                returncode=0, stdout=QDBUS_WINDOW_OUTPUT, stderr=""
            )
        if "kscreen-doctor" in cmd:
            return CommandResult(
                returncode=0, stdout=KSCREEN_OUTPUT, stderr=""
            )
        if cmd.startswith("spectacle"):
            # Write a fake PNG to the output path
            import re as _re

            m = _re.search(r"--output\s+(\S+)", cmd)
            if m:
                from pathlib import Path

                Path(m.group(1)).parent.mkdir(parents=True, exist_ok=True)
                Path(m.group(1)).write_bytes(fake_png)
            return CommandResult(returncode=0, stdout="", stderr="")
        if cmd.startswith("magick"):
            # Write a fake JPEG to the output path
            import re as _re

            parts = cmd.split()
            # magick input.png -quality 85 output.jpg
            jpg_path = parts[-1]
            from pathlib import Path

            Path(jpg_path).write_bytes(fake_jpg)
            return CommandResult(returncode=0, stdout="", stderr="")
        return CommandResult(returncode=1, stdout="", stderr="unknown command")

    mock_run.side_effect = side_effect

    jpeg_bytes, metadata = capture_active_window()

    assert jpeg_bytes == fake_jpg
    assert metadata["origin_x"] == 200
    assert metadata["origin_y"] == 100
    assert metadata["width"] == 1200
    assert metadata["height"] == 900
    assert metadata["scale"] == 1.0  # x=200 is on HDMI-A-2 (scale 1.0)
    assert metadata["caption"] == "Hello World - Firefox"

    # Verify spectacle was called with -a flag
    spectacle_calls = [
        c for c in mock_run.call_args_list if "spectacle" in str(c)
    ]
    assert len(spectacle_calls) == 1
    assert "-a" in str(spectacle_calls[0])

    get_monitor_info.cache_clear()
