from unittest.mock import MagicMock, patch

from fastmcp.utilities.types import Image

from bazzite_mcp.tools.desktop import screenshot
from bazzite_mcp.tools.desktop.input import _send_mouse


# --- screenshot tests ---


@patch("bazzite_mcp.tools.desktop.capture.run_command")
def test_screenshot_window_default_captures_active(mock_run: MagicMock, tmp_path) -> None:
    """screenshot(target='window') captures the active window."""
    def fake_run(cmd):
        m = MagicMock()
        m.returncode = 0
        if "spectacle" in cmd:
            import re as _re
            path = _re.search(r"-o\s+(\S+)", cmd).group(1)
            from pathlib import Path
            Path(path).write_bytes(b"\x89PNGfake")
        return m
    mock_run.side_effect = fake_run
    result = screenshot(target="window")
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], Image)
    assert result[1] == "Captured active window"


@patch("bazzite_mcp.tools.desktop.capture.run_command")
@patch("bazzite_mcp.tools.desktop.capture._kwin_activate")
@patch("bazzite_mcp.tools.desktop.capture._resolve_window")
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
            path = _re.search(r"-o\s+(\S+)", cmd).group(1)
            from pathlib import Path
            Path(path).write_bytes(b"\x89PNGfake")
        return m
    mock_run.side_effect = fake_run
    result = screenshot(target="window", window="brave")
    mock_resolve.assert_called_once_with("brave")
    mock_activate.assert_called_once_with("some-uuid")
    assert isinstance(result[0], Image)


@patch("bazzite_mcp.tools.desktop.capture.run_command")
def test_screenshot_desktop_target(mock_run: MagicMock) -> None:
    """screenshot(target='desktop') captures the full desktop."""
    def fake_run(cmd):
        m = MagicMock()
        m.returncode = 0
        if "spectacle" in cmd:
            import re as _re
            path = _re.search(r"-o\s+(\S+)", cmd).group(1)
            from pathlib import Path
            Path(path).write_bytes(b"\x89PNGfake")
        return m

    mock_run.side_effect = fake_run
    result = screenshot(target="desktop")
    assert isinstance(result, list)
    assert result[1] == "Captured desktop"


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
