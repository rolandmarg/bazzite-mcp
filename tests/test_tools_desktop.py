from unittest.mock import MagicMock, patch

import pytest

from fastmcp.utilities.types import Image

from bazzite_mcp.runner import CommandResult, ToolError
from bazzite_mcp.tools.desktop import _screenshot_desktop, screenshot


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
