"""Structured error types for bazzite-mcp tools."""

from __future__ import annotations

from mcp.server.fastmcp.exceptions import ToolError


class CommandError(ToolError):
    """A command execution failed with structured context.

    Agents can inspect returncode, stdout, stderr to understand the failure
    without parsing error message strings.
    """

    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
        command: str | list[str] | None = None,
    ) -> None:
        detail = message
        if stderr:
            detail = f"{message}\nstderr: {stderr}"
        super().__init__(detail)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command = command


class CommandTimeoutError(CommandError):
    """A command exceeded its timeout."""

    def __init__(self, command: str | list[str], timeout: int) -> None:
        cmd_str = " ".join(command) if isinstance(command, list) else command
        super().__init__(
            f"Command timed out after {timeout}s: {cmd_str}",
            returncode=124,
            command=command,
        )
        self.timeout = timeout
