from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.system import _system_info_basic, system_info, manage_snapshots


@patch("bazzite_mcp.tools.system.run_command")
def test_system_info_basic(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Bazzite 43", stderr="")
    result = _system_info_basic()
    assert "Bazzite" in result


# --- Dispatcher tests ---


@patch("bazzite_mcp.tools.system.run_command")
def test_system_info_dispatcher_basic(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Bazzite 43", stderr="")
    result = system_info(detail="basic")
    assert "Bazzite" in result


@patch("bazzite_mcp.tools.system.run_command")
def test_system_info_dispatcher_full(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="GPU: NVIDIA RTX 3060 Ti", stderr="")
    result = system_info(detail="full")
    assert isinstance(result, str)


def test_manage_snapshots_diff_requires_snapshot_id() -> None:
    with pytest.raises(ToolError, match="snapshot_id"):
        manage_snapshots("diff")
