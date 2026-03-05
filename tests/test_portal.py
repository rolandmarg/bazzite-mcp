import json
from unittest.mock import MagicMock, patch

import pytest

from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.portal import PortalClient


class FakeProcess:
    """Simulates the portal_helper subprocess for testing."""

    def __init__(self, responses: list[dict]):
        self._responses = iter(responses)
        self.stdin = MagicMock()
        self.stdout = self
        self.stderr = MagicMock()
        self.pid = 12345
        self.returncode = None

    def readline(self):
        return json.dumps(next(self._responses)) + "\n"

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def wait(self, timeout=None):
        pass


@patch("bazzite_mcp.portal.subprocess.Popen")
def test_portal_client_connect_creates_session(mock_popen: MagicMock) -> None:
    proc = FakeProcess([
        {"ready": True},
        {"ok": True, "streams": [{"node_id": 42, "index": 0}]},
    ])
    mock_popen.return_value = proc
    client = PortalClient()
    result = client.connect()
    assert result["ok"] is True
    assert client.is_connected
    assert client._stream_node_id == 42


@patch("bazzite_mcp.portal.subprocess.Popen")
def test_portal_client_pointer_move(mock_popen: MagicMock) -> None:
    proc = FakeProcess([
        {"ready": True},
        {"ok": True, "streams": [{"node_id": 42, "index": 0}]},
        {"ok": True},
    ])
    mock_popen.return_value = proc
    client = PortalClient()
    client.connect()
    result = client.pointer_move(100.0, 200.0)
    assert result["ok"] is True
    # Verify the command written to stdin includes pointer_move
    calls = proc.stdin.write.call_args_list
    move_cmd = json.loads(calls[-1][0][0].strip())
    assert move_cmd["op"] == "pointer_move"
    assert move_cmd["x"] == 100.0
    assert move_cmd["y"] == 200.0
    assert move_cmd["stream"] == 42


@patch("bazzite_mcp.portal.subprocess.Popen")
def test_portal_client_click(mock_popen: MagicMock) -> None:
    proc = FakeProcess([
        {"ready": True},
        {"ok": True, "streams": [{"node_id": 42, "index": 0}]},
        {"ok": True},
    ])
    mock_popen.return_value = proc
    client = PortalClient()
    client.connect()
    result = client.click()
    assert result["ok"] is True
    # Verify the command written to stdin includes pointer_click
    calls = proc.stdin.write.call_args_list
    click_cmd = json.loads(calls[-1][0][0].strip())
    assert click_cmd["op"] == "pointer_click"
    assert click_cmd["button"] == 272
    assert click_cmd["action"] == "click"


def test_portal_client_not_connected_raises() -> None:
    client = PortalClient()
    with pytest.raises(ToolError, match="[Nn]ot connected"):
        client.pointer_move(0, 0)
