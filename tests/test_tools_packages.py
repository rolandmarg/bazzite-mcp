from unittest.mock import MagicMock, patch

from bazzite_mcp.runner import CommandResult
from bazzite_mcp.tools.packages import install_package, list_packages, search_package


@patch("bazzite_mcp.tools.packages.run_command")
def test_search_package(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="org.mozilla.firefox", stderr="")
    result = search_package("firefox")
    assert "firefox" in result.lower()


@patch("bazzite_mcp.tools.packages.run_command")
def test_list_packages_flatpak(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Firefox\nVLC", stderr="")
    result = list_packages(source="flatpak")
    assert "Firefox" in result


# --- install_package tests ---


@patch("bazzite_mcp.tools.packages.run_command")
def test_install_package_ujust_found_first(mock_run: MagicMock) -> None:
    """ujust path is tried first; when found, flatpak/brew are never called."""
    mock_run.return_value = CommandResult(
        returncode=0, stdout="install-firefox", stderr=""
    )
    result = install_package("firefox")
    assert "ujust" in result.lower()
    assert "install-firefox" in result
    # Only one call made (ujust --summary grep)
    assert mock_run.call_count == 1


@patch("bazzite_mcp.tools.packages.run_command")
def test_install_package_flatpak_fallback(mock_run: MagicMock) -> None:
    """When ujust finds nothing, flatpak is tried next."""
    mock_run.side_effect = [
        CommandResult(returncode=1, stdout="", stderr=""),    # ujust miss
        CommandResult(returncode=0, stdout="org.mozilla.firefox\tFirefox\t128", stderr=""),  # flatpak hit
    ]
    result = install_package("firefox")
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
    result = install_package("ripgrep")
    assert "brew" in result.lower() or "homebrew" in result.lower()
    assert "ripgrep" in result
