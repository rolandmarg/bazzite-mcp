import base64
from unittest.mock import MagicMock, patch

import pytest

from fastmcp.utilities.types import Image

from bazzite_mcp.runner import CommandResult, ToolError
from bazzite_mcp.tools.desktop import (
    _screenshot_desktop,
    _send_mouse,
    connect_portal,
    screenshot,
)


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_returns_image_with_jpeg(
    mock_run: MagicMock, mock_which: MagicMock
) -> None:
    mock_which.return_value = "/usr/bin/spectacle"
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = _screenshot_desktop()
    assert isinstance(result, Image)
    assert result.path is not None
    assert str(result.path).endswith(".jpg")
    assert "/tmp/bazzite-mcp/" in str(result.path)


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_calls_spectacle_then_magick(
    mock_run: MagicMock, mock_which: MagicMock
) -> None:
    mock_which.return_value = "/usr/bin/spectacle"
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    _screenshot_desktop()
    commands = [c[0][0] for c in mock_run.call_args_list]
    assert any("spectacle" in cmd for cmd in commands)
    assert any("magick" in cmd for cmd in commands)
    assert not any("-resize 5120x" in cmd for cmd in commands)


@patch("bazzite_mcp.tools.desktop.shutil.which")
def test_screenshot_raises_when_spectacle_missing(mock_which: MagicMock) -> None:
    mock_which.return_value = None
    try:
        _screenshot_desktop()
        assert False, "Should have raised"
    except Exception as e:
        assert "spectacle" in str(e).lower()


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_falls_back_to_png_without_magick(
    mock_run: MagicMock, mock_which: MagicMock
) -> None:
    def which_side_effect(name: str) -> str | None:
        return "/usr/bin/spectacle" if name == "spectacle" else None

    mock_which.side_effect = which_side_effect
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = _screenshot_desktop()
    assert isinstance(result, Image)
    assert str(result.path).endswith(".png")


# --- Dispatcher tests ---


def test_screenshot_dispatcher_window_requires_window() -> None:
    with pytest.raises(ToolError, match="window"):
        screenshot(target="window")


# --- Portal integration tests ---


@patch("bazzite_mcp.tools.desktop._get_portal")
def test_screenshot_uses_portal_when_connected(mock_get_portal: MagicMock) -> None:
    fake_jpeg = base64.b64encode(b"\xff\xd8fake_jpeg_data").decode()
    portal = MagicMock()
    portal.is_connected = True
    portal.grab_frame.return_value = {"jpeg_b64": fake_jpeg}
    mock_get_portal.return_value = portal
    result = _screenshot_desktop()
    portal.grab_frame.assert_called_once()
    assert isinstance(result, Image)


@patch("bazzite_mcp.tools.desktop._get_portal")
@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_falls_back_to_spectacle(
    mock_run: MagicMock, mock_which: MagicMock, mock_get_portal: MagicMock
) -> None:
    portal = MagicMock()
    portal.is_connected = False
    mock_get_portal.return_value = portal
    mock_which.return_value = "/usr/bin/spectacle"
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = _screenshot_desktop()
    assert isinstance(result, Image)
    commands = [c[0][0] for c in mock_run.call_args_list]
    assert any("spectacle" in cmd for cmd in commands)


@patch("bazzite_mcp.tools.desktop._get_portal")
def test_send_mouse_uses_portal_when_connected(mock_get_portal: MagicMock) -> None:
    portal = MagicMock()
    portal.is_connected = True
    portal.pointer_move.return_value = {"ok": True}
    portal.click.return_value = {"ok": True}
    mock_get_portal.return_value = portal
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
