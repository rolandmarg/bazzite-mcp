from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.containers import create_distrobox, list_distroboxes


@patch("bazzite_mcp.tools.containers.run_command")
def test_list_distroboxes(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="ubuntu-dev | running", stderr="")
    result = list_distroboxes()
    assert "ubuntu" in result.lower()


@patch("bazzite_mcp.tools.containers.run_audited")
def test_create_distrobox(mock_audited: MagicMock) -> None:
    mock_audited.return_value = MagicMock(returncode=0, stdout="Container created", stderr="")
    result = create_distrobox("test-box", image="ubuntu:24.04")
    assert "created" in result.lower() or "Container" in result
