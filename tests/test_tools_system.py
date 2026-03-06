from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.system import system_info, manage_snapshots
from bazzite_mcp.tools.system.info import _hardware_info, _system_info_basic


@patch("bazzite_mcp.tools.system.info.run_command")
def test_system_info_basic(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Bazzite 43", stderr="")
    result = _system_info_basic()
    assert "Bazzite" in result


# --- Dispatcher tests ---


@patch("bazzite_mcp.tools.system.info.run_command")
def test_system_info_dispatcher_basic(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Bazzite 43", stderr="")
    result = system_info(detail="basic")
    assert "Bazzite" in result


@patch("bazzite_mcp.tools.system.info.run_command")
def test_system_info_dispatcher_full(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="GPU: NVIDIA RTX 3060 Ti", stderr="")
    result = system_info(detail="full")
    assert isinstance(result, str)


LSPCI_WITH_FALSE_POSITIVE = (
    "00:17.0 SATA controller: Intel Corporation Device 43d2 (rev 11)\n"
    "01:00.0 VGA compatible controller: NVIDIA Corporation GA104 "
    "[GeForce RTX 3060 Ti Lite Hash Rate] (rev a1)\n"
    "01:00.1 Audio device: NVIDIA Corporation GA104 High Definition Audio Controller (rev a1)"
)


@patch("bazzite_mcp.tools.system.info.run_command")
def test_gpu_detection_ignores_hex_device_ids(mock_run: MagicMock) -> None:
    """Regression: '3d' in '43d2' must not match as a GPU."""
    mock_run.return_value = MagicMock(returncode=0, stdout=LSPCI_WITH_FALSE_POSITIVE, stderr="")
    result = _system_info_basic()
    # Extract the GPU line from the formatted output
    gpu_line = [l for l in result.splitlines() if l.startswith("GPU:")][0]
    assert "NVIDIA" in gpu_line
    assert "SATA" not in gpu_line


LSPCI_V_WITH_FALSE_POSITIVE = (
    "00:17.0 SATA controller: Intel Corporation Device 43d2 (rev 11)\n"
    "\tSubsystem: Gigabyte Technology Co., Ltd Device b005\n"
    "\tFlags: bus master\n"
    "\n"
    "01:00.0 VGA compatible controller: NVIDIA Corporation GA104 [GeForce RTX 3060 Ti] (rev a1)\n"
    "\tSubsystem: Gigabyte Technology Co., Ltd Device 405a\n"
    "\tFlags: bus master, fast devsel\n"
    "\tMemory at 52000000 (32-bit, non-prefetchable) [size=16M]\n"
    "\tKernel driver in use: nvidia\n"
)


@patch("bazzite_mcp.tools.system.info.run_command")
def test_hardware_info_gpu_ignores_hex_device_ids(mock_run: MagicMock) -> None:
    """Regression: _hardware_info must pick VGA line, not SATA with 43d2."""
    mock_run.return_value = MagicMock(returncode=0, stdout=LSPCI_V_WITH_FALSE_POSITIVE, stderr="")
    result = _hardware_info()
    assert "NVIDIA" in result
    # GPU section should not contain the SATA controller
    gpu_section = result.split("=== GPU ===")[1].split("===")[0]
    assert "SATA" not in gpu_section


def test_manage_snapshots_diff_requires_snapshot_id() -> None:
    with pytest.raises(ToolError, match="snapshot_id"):
        manage_snapshots("diff")
