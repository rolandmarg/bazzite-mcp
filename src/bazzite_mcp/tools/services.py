from bazzite_mcp.runner import run_command


def manage_service(name: str, action: str, user: bool = False) -> str:
    """Start, stop, restart, enable, or disable a systemd service."""
    valid_actions = [
        "start",
        "stop",
        "restart",
        "enable",
        "disable",
        "enable --now",
        "disable --now",
    ]
    if action not in valid_actions:
        return f"Unknown action '{action}'. Supported: {', '.join(valid_actions)}."

    scope = "--user" if user else ""
    result = run_command(f"systemctl {scope} {action} {name}")
    if result.returncode != 0:
        return f"Failed to {action} {name}: {result.stderr}"
    return f"Service '{name}' {action} successful."


def service_status(name: str, user: bool = False) -> str:
    """Get status of a systemd service."""
    scope = "--user" if user else ""
    result = run_command(f"systemctl {scope} status {name} --no-pager")
    return result.stdout if result.stdout else result.stderr


def list_services(state: str | None = None, user: bool = False) -> str:
    """List systemd services, optionally filtered by state."""
    scope = "--user" if user else ""
    if state in ("running", "failed"):
        result = run_command(
            f"systemctl {scope} list-units --type=service --state={state} --no-pager"
        )
    elif state in ("enabled", "disabled"):
        result = run_command(
            f"systemctl {scope} list-unit-files --type=service --state={state} --no-pager"
        )
    else:
        result = run_command(f"systemctl {scope} list-units --type=service --no-pager")
    return result.stdout


def network_status() -> str:
    """Show NetworkManager connections, interfaces, and IP info."""
    parts: list[str] = []

    result = run_command("nmcli general status")
    parts.append(f"=== General ===\n{result.stdout}")

    result = run_command("nmcli connection show --active")
    parts.append(f"=== Active Connections ===\n{result.stdout}")

    result = run_command("ip -brief addr show")
    parts.append(f"=== IP Addresses ===\n{result.stdout}")

    return "\n\n".join(parts)


def manage_connection(action: str, name: str | None = None, **kwargs: str) -> str:
    """Create, modify, or delete NetworkManager connections."""
    if action == "show":
        result = run_command("nmcli connection show")
    elif action in ("up", "down", "delete") and name:
        result = run_command(f'nmcli connection {action} "{name}"')
    elif action == "modify" and name:
        props = " ".join(f"{key} {value}" for key, value in kwargs.items())
        result = run_command(f'nmcli connection modify "{name}" {props}')
    else:
        return "Usage: action='show|up|down|delete|modify', name=<connection name>"

    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_firewall(
    action: str,
    port: str | None = None,
    service: str | None = None,
) -> str:
    """Manage firewalld rules."""
    if action == "list":
        result = run_command("firewall-cmd --list-all")
    elif action == "add-port" and port:
        result = run_command(
            f"sudo firewall-cmd --add-port={port} --permanent && sudo firewall-cmd --reload"
        )
    elif action == "remove-port" and port:
        result = run_command(
            f"sudo firewall-cmd --remove-port={port} --permanent && sudo firewall-cmd --reload"
        )
    elif action == "add-service" and service:
        result = run_command(
            f"sudo firewall-cmd --add-service={service} --permanent && sudo firewall-cmd --reload"
        )
    elif action == "remove-service" and service:
        result = run_command(
            f"sudo firewall-cmd --remove-service={service} --permanent && sudo firewall-cmd --reload"
        )
    else:
        return "Usage: action='list|add-port|remove-port|add-service|remove-service'"

    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_tailscale(action: str) -> str:
    """Manage Tailscale VPN."""
    valid = ["status", "up", "down", "ip", "peers"]
    if action not in valid:
        return f"Unknown action '{action}'. Supported: {', '.join(valid)}."

    if action == "peers":
        result = run_command("tailscale status")
    elif action == "ip":
        result = run_command("tailscale ip")
    else:
        result = run_command(f"tailscale {action}")

    if result.returncode == 0:
        return result.stdout
    return (
        f"Error: {result.stderr}\n\n"
        "Tip: if Tailscale is not enabled, run ujust_run('enable-tailscale') first."
    )
