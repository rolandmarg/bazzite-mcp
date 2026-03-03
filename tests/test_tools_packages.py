from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.packages import list_packages, search_package


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
