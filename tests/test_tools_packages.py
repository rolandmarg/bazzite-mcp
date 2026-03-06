import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import CommandResult, ToolError
from bazzite_mcp.tools.core.packages import (
    _install_package,
    _list_packages,
    _search_package,
    packages,
)


@patch("bazzite_mcp.tools.core.packages.run_command")
def test_search_package(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0, stdout="org.mozilla.firefox", stderr=""
    )
    result = _search_package("firefox")
    assert "firefox" in result.lower()


@patch("bazzite_mcp.tools.core.packages.run_command")
def test_list_packages_flatpak(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Firefox\nVLC", stderr="")
    result = _list_packages(source="flatpak")
    assert "Firefox" in result


# --- install_package tests ---


@patch("bazzite_mcp.tools.core.packages.run_audited")
def test_install_package_requires_explicit_method(mock_run_audited: MagicMock) -> None:
    mock_run_audited.return_value = CommandResult(returncode=0, stdout="ok", stderr="")
    result = _install_package("firefox", "flatpak")
    assert "Installed 'firefox' via flatpak" in result
    mock_run_audited.assert_called_once()


@patch("bazzite_mcp.tools.core.packages.run_command")
def test_search_package_sets_brew_no_auto_update(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        CommandResult(returncode=1, stdout="", stderr=""),
        CommandResult(returncode=1, stdout="", stderr=""),
        CommandResult(returncode=1, stdout="", stderr=""),
    ]
    result = _search_package("virt-manager")
    assert "No results" in result
    assert any(
        call.args[0] == ["brew", "search", "virt-manager"]
        and call.kwargs.get("env") == {"HOMEBREW_NO_AUTO_UPDATE": "1"}
        for call in mock_run.call_args_list
    )


@patch("bazzite_mcp.tools.core.packages.run_command")
def test_search_package_continues_on_timeout(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        CommandResult(returncode=1, stdout="", stderr=""),
        subprocess.TimeoutExpired(cmd="flatpak search virt-manager", timeout=20),
        CommandResult(returncode=1, stdout="", stderr=""),
    ]
    result = _search_package("virt-manager")
    assert "timed out querying flatpak" in result


# --- Dispatcher tests ---


def test_packages_dispatcher_install_requires_package() -> None:
    with pytest.raises(ToolError, match="package"):
        packages(action="install")


def test_packages_dispatcher_install_requires_method() -> None:
    with pytest.raises(ToolError, match="package.*method"):
        packages(action="install", package="firefox")


def test_packages_dispatcher_remove_requires_both() -> None:
    with pytest.raises(ToolError, match="package.*method"):
        packages(action="remove", package="firefox")
