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


@patch("bazzite_mcp.tools.desktop.capture_active_window")
def test_screenshot_window_default_captures_active(mock_capture: MagicMock) -> None:
    """screenshot(target='window') without window arg captures active window."""
    mock_capture.return_value = (
        b"\xff\xd8fake_jpeg",
        {"origin_x": 100, "origin_y": 50, "scale": 1.0, "width": 800, "height": 600, "caption": "Test Window"},
    )
    result = screenshot(target="window")
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], Image)
    assert "Test Window" in result[1]
    assert "(800x600)" in result[1]
    mock_capture.assert_called_once()


@patch("bazzite_mcp.tools.desktop._kwin_activate")
@patch("bazzite_mcp.tools.desktop._resolve_window")
@patch("bazzite_mcp.tools.desktop.capture_active_window")
def test_screenshot_window_with_name_activates_first(
    mock_capture: MagicMock, mock_resolve: MagicMock, mock_activate: MagicMock
) -> None:
    """screenshot(target='window', window='brave') activates it first."""
    mock_resolve.return_value = "some-uuid"
    mock_capture.return_value = (
        b"\xff\xd8fake_jpeg",
        {"origin_x": 200, "origin_y": 100, "scale": 1.5, "width": 1200, "height": 900, "caption": "Brave"},
    )
    result = screenshot(target="window", window="brave")
    mock_resolve.assert_called_once_with("brave")
    mock_activate.assert_called_once_with("some-uuid")
    assert isinstance(result[0], Image)
    assert "Brave" in result[1]


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


@patch("bazzite_mcp.tools.desktop.capture_active_window")
def test_screenshot_sets_last_meta(mock_capture: MagicMock) -> None:
    """screenshot(target='window') sets _last_screenshot_meta for send_input."""
    meta = {"origin_x": 200, "origin_y": 100, "scale": 1.5, "width": 1200, "height": 900, "caption": "Test"}
    mock_capture.return_value = (b"\xff\xd8fake", meta)
    screenshot(target="window")
    assert desktop_mod._last_screenshot_meta == meta


# --- Coordinate offset in send_input ---


@patch("bazzite_mcp.tools.desktop._get_portal")
def test_send_mouse_applies_coordinate_offset(mock_get_portal: MagicMock) -> None:
    """When _last_screenshot_meta is set, mouse coordinates are offset."""
    portal = MagicMock()
    portal.is_connected = True
    portal.pointer_move.return_value = {"ok": True}
    portal.click.return_value = {"ok": True}
    mock_get_portal.return_value = portal

    # Set screenshot metadata: window at (200, 100) with scale 2.0
    desktop_mod._last_screenshot_meta = {
        "origin_x": 200,
        "origin_y": 100,
        "scale": 2.0,
    }
    try:
        _send_mouse("click", 400, 300)
        # Expected: abs_x = 200 + 400/2.0 = 400.0, abs_y = 100 + 300/2.0 = 250.0
        portal.pointer_move.assert_called_once_with(400.0, 250.0)
    finally:
        desktop_mod._last_screenshot_meta = None


@patch("bazzite_mcp.tools.desktop._get_portal")
def test_send_mouse_no_offset_when_no_meta(mock_get_portal: MagicMock) -> None:
    """When _last_screenshot_meta is None, raw coordinates are used."""
    portal = MagicMock()
    portal.is_connected = True
    portal.pointer_move.return_value = {"ok": True}
    portal.click.return_value = {"ok": True}
    mock_get_portal.return_value = portal

    desktop_mod._last_screenshot_meta = None
    _send_mouse("click", 500, 300)
    portal.pointer_move.assert_called_once_with(500.0, 300.0)


# --- Portal integration tests ---


@patch("bazzite_mcp.tools.desktop._get_portal")
def test_send_mouse_uses_portal_when_connected(mock_get_portal: MagicMock) -> None:
    portal = MagicMock()
    portal.is_connected = True
    portal.pointer_move.return_value = {"ok": True}
    portal.click.return_value = {"ok": True}
    mock_get_portal.return_value = portal
    desktop_mod._last_screenshot_meta = None
    result = _send_mouse("click", 500, 300)
    portal.pointer_move.assert_called_once_with(500.0, 300.0)
    portal.click.assert_called_once()
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
