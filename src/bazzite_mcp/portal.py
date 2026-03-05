"""Portal client — manages the portal_helper subprocess."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

_SYSTEM_PYTHON = "/usr/bin/python3"
_HELPER_MODULE = str(Path(__file__).parent / "portal_helper.py")


class PortalClient:
    """Manages the portal_helper subprocess and provides a sync API."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._stream_node_id: int = 0
        self.is_connected: bool = False

    def connect(self) -> dict:
        """Start helper subprocess and create portal session."""
        if self.is_connected:
            return {"status": "already_active"}

        self._proc = subprocess.Popen(
            [_SYSTEM_PYTHON, _HELPER_MODULE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for ready signal
        ready = self._read_response()
        if not ready.get("ready"):
            raise ToolError(f"Portal helper failed to start: {ready}")

        # Create the portal session (triggers KDE auth dialog)
        result = self._send({"op": "create"})
        if result.get("error"):
            raise ToolError(f"Portal session failed: {result['error']}")

        # Extract stream_node_id from streams array or direct field
        streams = result.get("streams", [])
        if streams:
            self._stream_node_id = streams[0].get("node_id", 0)
        else:
            self._stream_node_id = result.get("stream_node_id", 0)

        self.is_connected = True
        return result

    def pointer_move(self, x: float, y: float) -> dict:
        """Send pointer_move command with stream_node_id."""
        self._require_connected()
        return self._send({
            "op": "pointer_move",
            "stream": self._stream_node_id,
            "x": x,
            "y": y,
        })

    def click(self, button: int = 272, action: str = "click") -> dict:
        """Send pointer_click command."""
        self._require_connected()
        return self._send({
            "op": "pointer_click",
            "button": button,
            "action": action,
        })

    def key_press(self, keysym: int, is_keysym: bool = True) -> dict:
        """Send key_press command."""
        self._require_connected()
        return self._send({
            "op": "key_press",
            "keysym": keysym,
            "is_keysym": is_keysym,
        })

    def grab_frame(self) -> dict:
        """Send grab_frame command, returns dict with jpeg_b64."""
        self._require_connected()
        return self._send({"op": "grab_frame"})

    def close(self) -> None:
        """Send close command and terminate subprocess."""
        if self._proc and self._proc.poll() is None:
            try:
                self._send({"op": "close"})
            except Exception:
                pass
            self._proc.terminate()
            self._proc.wait(timeout=5)
        self._proc = None
        self.is_connected = False

    def _require_connected(self) -> None:
        """Raise ToolError if not connected."""
        if not self.is_connected or not self._proc or self._proc.poll() is not None:
            raise ToolError("Portal not connected. Call connect() first.")

    def _send(self, cmd: dict) -> dict:
        """Write JSON command to subprocess stdin, read JSON response."""
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise ToolError("Portal helper process not running.")
        self._proc.stdin.write(json.dumps(cmd) + "\n")
        self._proc.stdin.flush()
        return self._read_response()

    def _read_response(self) -> dict:
        """Read one JSON line from subprocess stdout."""
        if not self._proc or not self._proc.stdout:
            raise ToolError("Portal helper process not running.")
        line = self._proc.stdout.readline()
        if not line:
            stderr = ""
            if self._proc.stderr:
                stderr = self._proc.stderr.read()
            raise ToolError(f"Portal helper died. stderr: {stderr[:500]}")
        return json.loads(line)


# Module-level singleton
_client: PortalClient | None = None


def get_portal() -> PortalClient:
    """Get or create the singleton portal client (does NOT auto-connect)."""
    global _client
    if _client is None:
        _client = PortalClient()
    return _client
