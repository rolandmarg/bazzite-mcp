import shlex

from bazzite_mcp.runner import run_audited, run_command


def ujust_list(filter: str | None = None) -> str:
    """List available ujust commands, optionally filtered by keyword."""
    result = run_command("ujust --summary")
    if result.returncode != 0:
        result = run_command("ujust")
        if result.returncode != 0:
            return f"Error listing ujust commands: {result.stderr}"

    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    if filter:
        lines = [line for line in lines if filter.lower() in line.lower()]
    return "\n".join(lines) if lines else "No matching commands found."


def ujust_show(command: str) -> str:
    """Show the source script of a ujust command before running it."""
    result = run_command(f"ujust --show {shlex.quote(command)}")
    if result.returncode != 0:
        return f"Error showing command '{command}': {result.stderr}"
    return result.stdout


def ujust_run(command: str) -> str:
    """Execute a ujust command.

    ujust is Bazzite's built-in command runner for system setup, configuration,
    and maintenance. It is the first method to check for system operations.
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        return "Invalid command syntax."

    if not parts:
        return "Missing ujust command."

    recipe = parts[0]
    if len(parts) >= 2 and parts[1] in {"help", "--help", "-h"}:
        usage = run_command(f"ujust --usage {shlex.quote(recipe)}")
        if usage.returncode == 0 and usage.stdout.strip():
            return usage.stdout
        fallback = run_command(f"ujust --show {shlex.quote(recipe)}")
        if fallback.returncode == 0 and fallback.stdout.strip():
            return fallback.stdout
        return f"Could not retrieve usage for '{recipe}'."

    recipe_source = run_command(f"ujust --show {shlex.quote(recipe)}")
    if (
        recipe_source.returncode == 0
        and len(parts) == 1
        and "Choose" in recipe_source.stdout
    ):
        return (
            f"'{recipe}' appears interactive. Pass an explicit non-interactive option "
            "(for example: '<recipe> help') or inspect it with ujust_show first."
        )

    result = run_audited(
        f"ujust {shlex.join(parts)}",
        tool="ujust_run",
        args={"command": command},
    )
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    if result.returncode != 0:
        output = f"Command failed (exit {result.returncode}):\n{output}"
    return output
