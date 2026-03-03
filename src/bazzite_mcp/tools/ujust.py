from bazzite_mcp.runner import run_command


def ujust_list(filter: str | None = None) -> str:
    """List available ujust commands, optionally filtered by keyword."""
    result = run_command("ujust --summary 2>/dev/null || ujust 2>&1")
    if result.returncode != 0:
        return f"Error listing ujust commands: {result.stderr}"

    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    if filter:
        lines = [line for line in lines if filter.lower() in line.lower()]
    return "\n".join(lines) if lines else "No matching commands found."


def ujust_show(command: str) -> str:
    """Show the source script of a ujust command before running it."""
    result = run_command(f"ujust --show {command}")
    if result.returncode != 0:
        return f"Error showing command '{command}': {result.stderr}"
    return result.stdout


def ujust_run(command: str) -> str:
    """Execute a ujust command.

    ujust is Bazzite's built-in command runner for system setup, configuration,
    and maintenance. It is the first method to check for system operations.
    """
    result = run_command(f"ujust {command}")
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    if result.returncode != 0:
        output = f"Command failed (exit {result.returncode}):\n{output}"
    return output
