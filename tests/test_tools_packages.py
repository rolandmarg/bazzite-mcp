import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import CommandResult, ToolError
from bazzite_mcp.tools.packages import _install_package, _list_packages, _search_package, packages


@patch("bazzite_mcp.tools.packages.run_command")
def test_search_package(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0, stdout="org.mozilla.firefox", stderr=""
    )
    result = _search_package("firefox")
    assert "firefox" in result.lower()


@patch("bazzite_mcp.tools.packages.run_command")
def test_list_packages_flatpak(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Firefox\nVLC", stderr="")
    result = _list_packages(source="flatpak")
    assert "Firefox" in result


# --- install_package tests ---


@patch("bazzite_mcp.tools.packages.run_command")
def test_install_package_ujust_found_first(mock_run: MagicMock) -> None:
    """ujust path is tried first; when found, flatpak/brew are never called."""
    mock_run.return_value = CommandResult(
        returncode=0, stdout="install-firefox", stderr=""
    )
    result = _install_package("firefox")
    assert "ujust" in result.lower()
    assert "install-firefox" in result
    assert mock_run.call_count == 1


@patch("bazzite_mcp.tools.packages.run_command")
def test_install_package_flatpak_fallback(mock_run: MagicMock) -> None:
    """When ujust finds nothing, flatpak is tried next."""
    mock_run.side_effect = [
        CommandResult(returncode=1, stdout="", stderr=""),  # ujust miss
        CommandResult(
            returncode=0, stdout="org.mozilla.firefox\tFirefox\t128", stderr=""
        ),  # flatpak hit
    ]
    result = _install_package("firefox")
    assert "flatpak" in result.lower()
    assert "org.mozilla.firefox" in result


@patch("bazzite_mcp.tools.packages.run_command")
def test_install_package_brew_fallback_cli(mock_run: MagicMock) -> None:
    """When ujust and flatpak find nothing, brew is tried."""
    mock_run.side_effect = [
        CommandResult(returncode=1, stdout="", stderr=""),  # ujust miss
        CommandResult(returncode=1, stdout="", stderr=""),  # flatpak miss
        CommandResult(returncode=0, stdout="ripgrep", stderr=""),  # brew hit
    ]
    result = _install_package("ripgrep")
    assert "brew" in result.lower() or "homebrew" in result.lower()
    assert "ripgrep" in result


@patch("bazzite_mcp.tools.packages.run_command")
def test_search_package_sets_brew_no_auto_update(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        CommandResult(returncode=1, stdout="", stderr=""),
        CommandResult(returncode=1, stdout="", stderr=""),
        CommandResult(returncode=1, stdout="", stderr=""),
    ]
    result = _search_package("virt-manager")
    assert "No results" in result
    assert any(
        "HOMEBREW_NO_AUTO_UPDATE=1 brew search" in str(call.args[0])
        for call in mock_run.call_args_list
    )


@patch("bazzite_mcp.tools.packages.run_command")
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


def test_packages_dispatcher_remove_requires_both() -> None:
    with pytest.raises(ToolError, match="package.*method"):
        packages(action="remove", package="firefox")
