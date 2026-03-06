"""Tests for screen geometry helpers."""

from unittest.mock import MagicMock, patch

from bazzite_mcp.runner import CommandResult
from bazzite_mcp.screen_geometry import get_monitor_info

KSCREEN_OUTPUT = (
    "\x1b[01;32mOutput: \x1b[0;0m1 HDMI-A-1 73ff556f-3261-405a-abc6-c92363fc4073\n"
    "\tenabled\n"
    "\tconnected\n"
    "\tpriority 2\n"
    "\tGeometry: 2560,169 2560x1440\n"
    "\tScale: 1.5\n"
    "\tRotation: 1\n"
    "\x1b[01;32mOutput: \x1b[0;0m2 HDMI-A-2 df58f18c-66b5-4d20-9c49-7a52ba92e3bc\n"
    "\tenabled\n"
    "\tconnected\n"
    "\tpriority 1\n"
    "\tGeometry: 0,0 2560x1440\n"
    "\tScale: 1\n"
    "\tRotation: 1\n"
)


@patch("bazzite_mcp.screen_geometry.run_command")
def test_get_monitor_info(mock_run: MagicMock) -> None:
    get_monitor_info.cache_clear()
    mock_run.return_value = CommandResult(returncode=0, stdout=KSCREEN_OUTPUT, stderr="")

    monitors = get_monitor_info()

    assert monitors["HDMI-A-1"] == {"x": 2560, "y": 169, "w": 2560, "h": 1440, "scale": 1.5}
    assert monitors["HDMI-A-2"] == {"x": 0, "y": 0, "w": 2560, "h": 1440, "scale": 1.0}

    get_monitor_info.cache_clear()
