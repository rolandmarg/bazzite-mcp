import subprocess
from dataclasses import dataclass

from bazzite_mcp.guardrails import check_command


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    warning: str | None = None


def run_command(command: str, timeout: int = 120) -> CommandResult:
    check = check_command(command)
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
        warning=check.warning,
    )
