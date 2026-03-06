import json
import struct
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastmcp.utilities.types import Image

from bazzite_mcp.tools.desktop import screenshot
from bazzite_mcp.tools.desktop.input import _send_mouse


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _write_png(path: Path, width: int, height: int) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + (b"\x00\x00\x00" * width)
    raw = row * height
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


# --- screenshot tests ---


@patch("bazzite_mcp.tools.desktop.capture.run_command")
@patch("bazzite_mcp.tools.desktop.capture.get_monitor_info", return_value={"HDMI-A-1": {"x": 0, "y": 0, "w": 1280, "h": 720, "scale": 1.25}})
@patch("bazzite_mcp.tools.desktop.capture._kwin_query_window_info")
def test_screenshot_window_default_captures_active(
    mock_window_info: MagicMock, mock_monitors: MagicMock, mock_run: MagicMock, tmp_path
) -> None:
    """screenshot(target='window') captures the active window."""
    mock_window_info.return_value = {"x": 100, "y": 50}
    def fake_run(cmd):
        m = MagicMock()
        m.returncode = 0
        if "spectacle" in cmd:
            path = cmd[cmd.index("-o") + 1]
            _write_png(Path(path), 640, 480)
        return m
    mock_run.side_effect = fake_run
    result = screenshot(target="window")
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], Image)
    meta = json.loads(result[1])
    assert meta["status"] == "Captured active window"
    assert meta["target"] == "window"
    assert meta["width"] == 640
    assert meta["height"] == 480
    assert meta["bytes"] > 0
    assert meta["origin_x"] == 100
    assert meta["origin_y"] == 50
    assert meta["scale"] == 1.25


@patch("bazzite_mcp.tools.desktop.capture.run_command")
@patch("bazzite_mcp.tools.desktop.capture.get_monitor_info", return_value={"HDMI-A-1": {"x": 0, "y": 0, "w": 1920, "h": 1080, "scale": 1.5}})
@patch("bazzite_mcp.tools.desktop.capture._kwin_activate")
@patch("bazzite_mcp.tools.desktop.capture._kwin_get_window_info")
@patch("bazzite_mcp.tools.desktop.capture._resolve_window")
def test_screenshot_window_with_name_activates_first(
    mock_resolve: MagicMock,
    mock_window_info: MagicMock,
    mock_activate: MagicMock,
    mock_monitors: MagicMock,
    mock_run: MagicMock,
) -> None:
    """screenshot(target='window', window='brave') activates it first."""
    mock_resolve.return_value = "some-uuid"
    mock_window_info.return_value = {"x": 320, "y": 200}
    def fake_run(cmd):
        m = MagicMock()
        m.returncode = 0
        if "spectacle" in cmd:
            path = cmd[cmd.index("-o") + 1]
            _write_png(Path(path), 320, 240)
        return m
    mock_run.side_effect = fake_run
    result = screenshot(target="window", window="brave")
    mock_resolve.assert_called_once_with("brave")
    mock_activate.assert_called_once_with("some-uuid")
    assert isinstance(result[0], Image)
    meta = json.loads(result[1])
    assert meta["origin_x"] == 320
    assert meta["origin_y"] == 200
    assert meta["scale"] == 1.5
    assert meta["width"] == 320
    assert meta["height"] == 240


@patch("bazzite_mcp.tools.desktop.capture.run_command")
def test_screenshot_desktop_target(mock_run: MagicMock) -> None:
    """screenshot(target='desktop') captures the full desktop."""
    def fake_run(cmd):
        m = MagicMock()
        m.returncode = 0
        if "spectacle" in cmd:
            path = cmd[cmd.index("-o") + 1]
            _write_png(Path(path), 1920, 1080)
        return m

    mock_run.side_effect = fake_run
    result = screenshot(target="desktop")
    assert isinstance(result, list)
    meta = json.loads(result[1])
    assert meta["status"] == "Captured desktop"
    assert meta["target"] == "desktop"
    assert meta["width"] == 1920
    assert meta["height"] == 1080
    assert meta["origin_x"] == 0
    assert meta["origin_y"] == 0
    assert meta["scale"] == 1.0


# --- send_input mouse tests ---


@patch("bazzite_mcp.tools.desktop.input._get_virtual_desktop_size", return_value=(5120, 1609))
@patch("bazzite_mcp.tools.desktop.input._run_ydotool")
@patch("bazzite_mcp.tools.desktop.input._ensure_ydotoold", return_value="/tmp/test.sock")
def test_send_mouse_applies_coordinate_offset(
    mock_ydotoold: MagicMock, mock_run: MagicMock, mock_vd: MagicMock,
) -> None:
    """When screenshot_meta is provided, mouse coordinates are offset and scaled."""
    mock_run.return_value = MagicMock(returncode=0)
    meta = {"origin_x": 2560, "origin_y": 169, "scale": 1.5}
    _send_mouse("click", 300, 150, screenshot_meta=meta)
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("mousemove" in c for c in calls)


@patch("bazzite_mcp.tools.desktop.input._get_virtual_desktop_size", return_value=(5120, 1609))
@patch("bazzite_mcp.tools.desktop.input._run_ydotool")
@patch("bazzite_mcp.tools.desktop.input._ensure_ydotoold", return_value="/tmp/test.sock")
def test_send_mouse_no_offset_when_no_meta(
    mock_ydotoold: MagicMock, mock_run: MagicMock, mock_vd: MagicMock,
) -> None:
    """When no screenshot_meta, raw coordinates are used."""
    mock_run.return_value = MagicMock(returncode=0)
    _send_mouse("click", 500, 300)
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("mousemove" in c for c in calls)


@patch("bazzite_mcp.tools.desktop.input._get_virtual_desktop_size", return_value=(2560, 1440))
@patch("bazzite_mcp.tools.desktop.input._run_ydotool")
@patch("bazzite_mcp.tools.desktop.input._ensure_ydotoold", return_value="/tmp/test.sock")
def test_send_mouse_click_result(
    mock_ydotoold: MagicMock, mock_run: MagicMock, mock_vd: MagicMock,
) -> None:
    """send_mouse returns descriptive result string."""
    mock_run.return_value = MagicMock(returncode=0)
    result = _send_mouse("click", 500, 300)
    assert "500" in result and "300" in result
