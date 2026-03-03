from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.settings import get_settings, set_theme


@patch("bazzite_mcp.tools.settings.run_command")
def test_set_theme_dark(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = set_theme("dark")
    assert "dark" in result.lower()


@patch("bazzite_mcp.tools.settings.run_command")
def test_get_settings(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="'prefer-dark'", stderr="")
    result = get_settings("org.gnome.desktop.interface", "color-scheme")
    assert "prefer-dark" in result
