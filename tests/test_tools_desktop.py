from unittest.mock import MagicMock, patch

import pytest

from fastmcp.utilities.types import Image

from bazzite_mcp.tools.desktop import (
    _last_screenshot_meta,
    _send_mouse,
    connect_portal,
    screenshot,
)
import bazzite_mcp.tools.desktop as desktop_mod


# --- screenshot() dispatcher with KWin screenshot module ---


@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_window_default_captures_active(mock_run: MagicMock, tmp_path) -> None:
    """screenshot(target='window') without window arg captures via spectacle."""
    # spectacle writes a PNG; magick converts to JPEG
    def fake_run(cmd):
        m = MagicMock()
        m.returncode = 0
        if "spectacle" in cmd:
            # Write fake PNG so the code can read it
            import re as _re
            path = _re.search(r"--output\s+(\S+)", cmd).group(1)
            from pathlib import Path
            Path(path).write_bytes(b"\x89PNGfake")
        elif "magick" in cmd:
            import re as _re
            parts = cmd.split()
            jpg_path = parts[-1]
            from pathlib import Path
            Path(jpg_path).write_bytes(b"\xff\xd8fake_jpeg")
        return m
    mock_run.side_effect = fake_run
    result = screenshot(target="window")
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], Image)


@patch("bazzite_mcp.tools.desktop.run_command")
@patch("bazzite_mcp.tools.desktop._kwin_activate")
@patch("bazzite_mcp.tools.desktop._resolve_window")
def test_screenshot_window_with_name_activates_first(
    mock_resolve: MagicMock, mock_activate: MagicMock, mock_run: MagicMock
) -> None:
    """screenshot(target='window', window='brave') activates it first."""
    mock_resolve.return_value = "some-uuid"
    def fake_run(cmd):
        m = MagicMock()
        m.returncode = 0
        if "spectacle" in cmd:
            import re as _re
            path = _re.search(r"--output\s+(\S+)", cmd).group(1)
            from pathlib import Path
            Path(path).write_bytes(b"\x89PNGfake")
        elif "magick" in cmd:
            parts = cmd.split()
            from pathlib import Path
            Path(parts[-1]).write_bytes(b"\xff\xd8fake_jpeg")
        return m
    mock_run.side_effect = fake_run
    result = screenshot(target="window", window="brave")
    mock_resolve.assert_called_once_with("brave")
    mock_activate.assert_called_once_with("some-uuid")
    assert isinstance(result[0], Image)


@patch("bazzite_mcp.tools.desktop.capture_screen")
def test_screenshot_monitor(mock_capture: MagicMock) -> None:
    """screenshot(target='monitor') uses capture_screen."""
    mock_capture.return_value = (
        b"\xff\xd8fake_jpeg",
        {"monitor": "HDMI-A-1", "origin_x": 0, "origin_y": 0, "width": 2560, "height": 1440, "scale": 1.0},
    )
    result = screenshot(target="monitor", monitor="HDMI-A-1")
    mock_capture.assert_called_once_with("HDMI-A-1")
    assert isinstance(result, list)
    assert "HDMI-A-1" in result[1]


@patch("bazzite_mcp.tools.desktop.capture_screen")
def test_screenshot_desktop_target(mock_capture: MagicMock) -> None:
    """screenshot(target='desktop') captures focused monitor."""
    mock_capture.return_value = (
        b"\xff\xd8fake_jpeg",
        {"monitor": "HDMI-A-1", "origin_x": 0, "origin_y": 0, "width": 2560, "height": 1440, "scale": 1.0},
    )
    result = screenshot(target="desktop")
    mock_capture.assert_called_once()
    assert isinstance(result, list)
    assert "HDMI-A-1" in result[1]


# --- screenshot sets _last_screenshot_meta ---


@patch("bazzite_mcp.tools.desktop.capture_screen")
def test_screenshot_sets_last_meta(mock_capture: MagicMock) -> None:
    """screenshot(target='monitor') sets _last_screenshot_meta for send_input."""
    meta = {"monitor": "HDMI-A-2", "origin_x": 0, "origin_y": 0, "scale": 1.0, "width": 2560, "height": 1440}
    mock_capture.return_value = (b"\xff\xd8fake", meta)
    screenshot(target="monitor")
    assert desktop_mod._last_screenshot_meta == meta


# --- Coordinate offset in send_input ---


@patch("bazzite_mcp.tools.desktop._get_virtual_desktop_size", return_value=(5120, 1609))
@patch("bazzite_mcp.tools.desktop.run_command")
@patch("bazzite_mcp.tools.desktop._ensure_ydotoold", return_value="/tmp/test.sock")
def test_send_mouse_applies_coordinate_offset(
    mock_ydotoold: MagicMock, mock_run: MagicMock, mock_vd: MagicMock,
) -> None:
    """When _last_screenshot_meta is set, mouse coordinates are offset and scaled."""
    mock_run.return_value = MagicMock(returncode=0)
    # Screenshot meta: monitor at (2560, 169) with scale 1.5
    desktop_mod._last_screenshot_meta = {
        "origin_x": 2560,
        "origin_y": 169,
        "scale": 1.5,
    }
    try:
        _send_mouse("click", 300, 150)
        # abs_x = 2560 + 300/1.5 = 2760.0, abs_y = 169 + 150/1.5 = 269.0
        # yd_x = int(2760/5120*32767) = 17663, yd_y = int(269/1609*32767) = 5479
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("mousemove --absolute" in c for c in calls)
    finally:
        desktop_mod._last_screenshot_meta = None


@patch("bazzite_mcp.tools.desktop._get_virtual_desktop_size", return_value=(5120, 1609))
@patch("bazzite_mcp.tools.desktop.run_command")
@patch("bazzite_mcp.tools.desktop._ensure_ydotoold", return_value="/tmp/test.sock")
def test_send_mouse_no_offset_when_no_meta(
    mock_ydotoold: MagicMock, mock_run: MagicMock, mock_vd: MagicMock,
) -> None:
    """When _last_screenshot_meta is None, raw coordinates are used."""
    mock_run.return_value = MagicMock(returncode=0)
    desktop_mod._last_screenshot_meta = None
    _send_mouse("click", 500, 300)
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("mousemove --absolute" in c for c in calls)


@patch("bazzite_mcp.tools.desktop._get_virtual_desktop_size", return_value=(2560, 1440))
@patch("bazzite_mcp.tools.desktop.run_command")
@patch("bazzite_mcp.tools.desktop._ensure_ydotoold", return_value="/tmp/test.sock")
def test_send_mouse_click_result(
    mock_ydotoold: MagicMock, mock_run: MagicMock, mock_vd: MagicMock,
) -> None:
    """send_mouse returns descriptive result string."""
    mock_run.return_value = MagicMock(returncode=0)
    desktop_mod._last_screenshot_meta = None
    result = _send_mouse("click", 500, 300)
    assert "500" in result and "300" in result


@patch("bazzite_mcp.tools.desktop._get_portal")
def test_connect_portal_creates_session(mock_get_portal: MagicMock) -> None:
    portal = MagicMock()
    portal.is_connected = False
    portal.connect.return_value = {"ok": True, "streams": [{"node_id": 42}]}
    mock_get_portal.return_value = portal
    result = connect_portal()
    assert "established" in result.lower() or "active" in result.lower()
    portal.connect.assert_called_once()
