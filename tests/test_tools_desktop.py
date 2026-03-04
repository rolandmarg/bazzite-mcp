from unittest.mock import MagicMock, patch

from fastmcp.utilities.types import Image

from bazzite_mcp.runner import CommandResult
from bazzite_mcp.tools.desktop import screenshot


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_returns_image_with_jpeg(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/spectacle"
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = screenshot()
    assert isinstance(result, Image)
    assert result.path is not None
    assert str(result.path).endswith(".jpg")
    assert "/tmp/bazzite-mcp/" in str(result.path)


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_calls_spectacle_then_magick(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/spectacle"
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    screenshot()
    commands = [c[0][0] for c in mock_run.call_args_list]
    assert any("spectacle" in cmd for cmd in commands)
    assert any("magick" in cmd for cmd in commands)


@patch("bazzite_mcp.tools.desktop.shutil.which")
def test_screenshot_raises_when_spectacle_missing(mock_which: MagicMock) -> None:
    mock_which.return_value = None
    try:
        screenshot()
        assert False, "Should have raised"
    except Exception as e:
        assert "spectacle" in str(e).lower()


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_falls_back_to_png_without_magick(mock_run: MagicMock, mock_which: MagicMock) -> None:
    def which_side_effect(name: str) -> str | None:
        return "/usr/bin/spectacle" if name == "spectacle" else None
    mock_which.side_effect = which_side_effect
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = screenshot()
    assert isinstance(result, Image)
    assert str(result.path).endswith(".png")
