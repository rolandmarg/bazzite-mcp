from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.settings import quick_setting, gsettings
from bazzite_mcp.tools.settings.quick import _set_theme
from bazzite_mcp.tools.settings.schema import _get_settings


@patch("bazzite_mcp.tools.settings.quick.run_audited")
def test_set_theme_dark(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = _set_theme("dark")
    assert "dark" in result.lower()


@patch("bazzite_mcp.tools.settings.schema.run_command")
def test_get_settings(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="'prefer-dark'", stderr="")
    result = _get_settings("org.gnome.desktop.interface", "color-scheme")
    assert "prefer-dark" in result


# --- Dispatcher tests ---


def test_quick_setting_theme_requires_mode() -> None:
    with pytest.raises(ToolError, match="mode"):
        quick_setting(setting="theme")


def test_quick_setting_power_requires_profile() -> None:
    with pytest.raises(ToolError, match="profile"):
        quick_setting(setting="power")


def test_gsettings_requires_schema_and_key() -> None:
    with pytest.raises(ToolError, match="schema.*key"):
        gsettings(action="get")
