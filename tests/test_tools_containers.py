from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.containers import (
    _create_distrobox,
    _list_distroboxes,
    manage_distrobox,
    manage_podman,
    manage_quadlet,
)


@patch("bazzite_mcp.tools.containers.distrobox.run_command")
def test_list_distroboxes(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0, stdout="ubuntu-dev | running", stderr=""
    )
    result = _list_distroboxes()
    assert "ubuntu" in result.lower()


@patch("bazzite_mcp.tools.containers.distrobox.run_audited")
def test_create_distrobox(mock_audited: MagicMock) -> None:
    mock_audited.return_value = MagicMock(
        returncode=0, stdout="Container created", stderr=""
    )
    result = _create_distrobox("test-box", image="ubuntu:24.04")
    assert "created" in result.lower() or "Container" in result


@patch("bazzite_mcp.tools.containers.podman.run_command")
def test_manage_podman_exec_uses_command(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    result = manage_podman("exec", container="box1", command="ls /")
    assert result == "ok"
    assert "podman exec" in mock_run.call_args[0][0]


@patch("bazzite_mcp.tools.containers.quadlet.Path.home")
@patch("bazzite_mcp.tools.containers.quadlet.run_audited")
def test_manage_quadlet_create_writes_unit(
    mock_audited: MagicMock, mock_home: MagicMock, tmp_path
) -> None:
    mock_home.return_value = tmp_path
    mock_audited.return_value = MagicMock(returncode=0, stdout="", stderr="")

    result = manage_quadlet(
        "create", name="demo", image="docker.io/library/nginx:latest"
    )

    unit_file = tmp_path / ".config" / "containers" / "systemd" / "demo.container"
    assert unit_file.exists()
    assert "Image=docker.io/library/nginx:latest" in unit_file.read_text(
        encoding="utf-8"
    )
    assert "Created Quadlet unit" in result


@patch("bazzite_mcp.tools.containers.quadlet.Path.home")
@patch("bazzite_mcp.tools.containers.quadlet.run_audited")
def test_manage_quadlet_remove_deletes_unit(
    mock_audited: MagicMock, mock_home: MagicMock, tmp_path
) -> None:
    mock_home.return_value = tmp_path
    mock_audited.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=0, stdout="", stderr=""),
    ]

    unit_file = tmp_path / ".config" / "containers" / "systemd" / "demo.container"
    unit_file.parent.mkdir(parents=True)
    unit_file.write_text("[Container]\nImage=test\n", encoding="utf-8")

    result = manage_quadlet("remove", name="demo")
    assert not unit_file.exists()
    assert "Removed Quadlet unit" in result


# --- Dispatcher tests ---


@patch("bazzite_mcp.tools.containers.distrobox.run_command")
def test_manage_distrobox_list(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="ubuntu-dev | running", stderr="")
    result = manage_distrobox("list")
    assert "ubuntu" in result.lower()


def test_manage_distrobox_create_requires_name() -> None:
    with pytest.raises(ToolError, match="name"):
        manage_distrobox("create")


def test_manage_distrobox_exec_requires_command() -> None:
    with pytest.raises(ToolError, match="command"):
        manage_distrobox("exec", name="box1")
