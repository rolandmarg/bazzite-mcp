import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def _ujust_list(filter: str | None = None) -> str:
    """List available ujust commands, optionally filtered by keyword."""
    result = run_command("ujust --summary")
    if result.returncode != 0:
        result = run_command("ujust")
        if result.returncode != 0:
            raise ToolError(f"Error listing ujust commands: {result.stderr}")

    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    if filter:
        lines = [line for line in lines if filter.lower() in line.lower()]
    return "\n".join(lines) if lines else "No matching commands found."


def _ujust_show(command: str) -> str:
    """Show the source script of a ujust command before running it."""
    result = run_command(f"ujust --show {shlex.quote(command)}")
    if result.returncode != 0:
        raise ToolError(f"Error showing command '{command}': {result.stderr}")
    return result.stdout


def _ujust_run(command: str) -> str:
    """Execute a ujust command."""
    try:
        parts = shlex.split(command)
    except ValueError:
        raise ToolError("Invalid command syntax.")

    if not parts:
        raise ToolError("Missing ujust command.")

    recipe = parts[0]
    if len(parts) >= 2 and parts[1] in {"help", "--help", "-h"}:
        usage = run_command(f"ujust --usage {shlex.quote(recipe)}")
        if usage.returncode == 0 and usage.stdout.strip():
            return usage.stdout
        fallback = run_command(f"ujust --show {shlex.quote(recipe)}")
        if fallback.returncode == 0 and fallback.stdout.strip():
            return fallback.stdout
        raise ToolError(f"Could not retrieve usage for '{recipe}'.")

    recipe_source = run_command(f"ujust --show {shlex.quote(recipe)}")
    if (
        recipe_source.returncode == 0
        and len(parts) == 1
        and "Choose" in recipe_source.stdout
    ):
        raise ToolError(
            f"'{recipe}' appears interactive. Pass an explicit non-interactive option "
            "(for example: '<recipe> help') or inspect it with action='show' first."
        )

    result = run_audited(
        f"ujust {shlex.join(parts)}",
        tool="ujust",
        args={"command": command},
    )
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    if result.returncode != 0:
        raise ToolError(f"Command failed (exit {result.returncode}):\n{output}")
    return output


def ujust(
    action: Literal["run", "list", "show"],
    command: str | None = None,
    filter: str | None = None,
) -> str:
    """Run, list, or inspect ujust commands — Bazzite's built-in system setup tool."""
    if action == "run":
        if not command:
            raise ToolError("'command' is required for action='run'.")
        return _ujust_run(command)
    if action == "show":
        if not command:
            raise ToolError("'command' is required for action='show'.")
        return _ujust_show(command)
    if action == "list":
        return _ujust_list(filter)
    raise ToolError(f"Unknown action '{action}'.")
