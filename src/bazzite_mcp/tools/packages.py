from __future__ import annotations

import json
import re
import shlex
import subprocess
from typing import Literal

from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.runner import CommandResult, run_audited, run_command


INSTALL_POLICY = """Bazzite 6-tier install hierarchy (official docs.bazzite.gg):
1. ujust - check ujust --summary for setup/install commands first
2. flatpak - primary method for GUI apps (via Flathub)
3. brew - CLI/TUI tools only (no GUI apps)
4. distrobox - for packages from other distro repos (apt, pacman, etc.)
5. AppImage - portable apps from trusted sources only
6. rpm-ostree - last resort. Can freeze updates, block rebasing, cause conflicts."""

SEARCH_TIMEOUT_SECONDS = 20


def _run_search_command(
    command: str, timeout: int = SEARCH_TIMEOUT_SECONDS
) -> CommandResult:
    """Run a search/listing command with bounded timeout and graceful timeout handling."""
    try:
        return run_command(command, timeout=timeout)
    except subprocess.TimeoutExpired:
        return CommandResult(
            returncode=124,
            stdout="",
            stderr=f"Timed out after {timeout}s",
        )


def install_package(
    package: str,
    method: Literal["flatpak", "brew", "rpm-ostree", "ujust"] | None = None,
) -> str:
    """Install package following Bazzite's 6-tier hierarchy, or use an explicit method.

    When no method is specified, searches ujust > flatpak > brew automatically.
    """
    if method:
        return _install_with_method(package, method)

    pkg = shlex.quote(package)
    ujust_summary = _run_search_command("ujust --summary 2>/dev/null")
    ujust_lines = (
        ujust_summary.stdout.strip().splitlines() if ujust_summary.stdout else []
    )
    matcher = re.compile(
        rf"install.*{re.escape(package)}|setup.*{re.escape(package)}", re.IGNORECASE
    )
    matches = [line for line in ujust_lines if matcher.search(line)]
    if ujust_summary.returncode == 0 and matches:
        commands = matches
        return (
            f"Found ujust command(s) for '{package}':\n"
            + "\n".join(f"  ujust {cmd.strip()}" for cmd in commands)
            + f"\n\nRun with: ujust_run tool\n\n{INSTALL_POLICY}"
        )

    flatpak_check = _run_search_command(f"flatpak search {pkg} 2>/dev/null")
    if flatpak_check.returncode == 0 and flatpak_check.stdout.strip():
        return (
            f"Flatpak results for '{package}':\n{flatpak_check.stdout}\n\n"
            f"Recommended: flatpak install flathub <app-id>\n\n{INSTALL_POLICY}"
        )

    brew_check = _run_search_command(
        f"HOMEBREW_NO_AUTO_UPDATE=1 brew search {pkg} 2>/dev/null"
    )
    if brew_check.returncode == 0 and brew_check.stdout.strip():
        return (
            f"Homebrew results for '{package}':\n{brew_check.stdout}\n\n"
            f"Recommended: brew install {package}\n\n{INSTALL_POLICY}"
        )

    return (
        f"Package '{package}' not found in ujust, flatpak, or brew.\n"
        "Consider: distrobox (other distro repos) or rpm-ostree (last resort).\n\n"
        f"{INSTALL_POLICY}"
    )


def _install_with_method(package: str, method: str) -> str:
    pkg = shlex.quote(package)
    method_commands = {
        "flatpak": f"flatpak install -y flathub {pkg}",
        "brew": f"brew install {pkg}",
        "rpm-ostree": f"rpm-ostree install {pkg}",
        "ujust": f"ujust {pkg}",
    }
    rollback_commands = {
        "flatpak": f"flatpak uninstall -y {pkg}",
        "brew": f"brew uninstall {pkg}",
        "rpm-ostree": f"rpm-ostree uninstall {pkg}",
    }
    if method not in method_commands:
        raise ToolError(
            f"Unknown method '{method}'. Supported: {', '.join(method_commands.keys())}"
        )

    result = run_audited(
        method_commands[method],
        tool="install_package",
        args={"package": package, "method": method},
        rollback=rollback_commands.get(method),
    )
    output = result.stdout
    if result.stderr:
        output += f"\n{result.stderr}"
    if result.returncode != 0:
        raise ToolError(f"Installation failed (exit {result.returncode}):\n{output}")
    return f"Installed '{package}' via {method}:\n{output}"


def remove_package(
    package: str, method: Literal["flatpak", "brew", "rpm-ostree"]
) -> str:
    """Remove package via its original install method."""
    pkg = shlex.quote(package)
    method_commands = {
        "flatpak": f"flatpak uninstall -y {pkg}",
        "brew": f"brew uninstall {pkg}",
        "rpm-ostree": f"rpm-ostree uninstall {pkg}",
    }
    reinstall_commands = {
        "flatpak": f"flatpak install -y flathub {pkg}",
        "brew": f"brew install {pkg}",
        "rpm-ostree": f"rpm-ostree install {pkg}",
    }
    if method not in method_commands:
        raise ToolError(
            f"Unknown method '{method}'. Supported: {', '.join(method_commands.keys())}"
        )

    result = run_audited(
        method_commands[method],
        tool="remove_package",
        args={"package": package, "method": method},
        rollback=reinstall_commands.get(method),
    )
    if result.returncode != 0:
        raise ToolError(
            f"Removal failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def search_package(package: str) -> str:
    """Search package across ujust, flatpak, brew."""
    parts: list[str] = []
    timed_out: list[str] = []

    pkg = shlex.quote(package)
    ujust_check = _run_search_command("ujust --summary 2>/dev/null")
    if ujust_check.returncode == 124:
        timed_out.append("ujust")
    if ujust_check.returncode == 0 and ujust_check.stdout.strip():
        matching_lines = [
            line
            for line in ujust_check.stdout.splitlines()
            if package.lower() in line.lower()
        ]
        if matching_lines:
            parts.append("[Tier 1 - ujust]\n" + "\n".join(matching_lines))

    flatpak_check = _run_search_command(f"flatpak search {pkg} 2>/dev/null")
    if flatpak_check.returncode == 124:
        timed_out.append("flatpak")
    if flatpak_check.returncode == 0 and flatpak_check.stdout.strip():
        parts.append(f"[Tier 2 - Flatpak]\n{flatpak_check.stdout}")

    brew_check = _run_search_command(
        f"HOMEBREW_NO_AUTO_UPDATE=1 brew search {pkg} 2>/dev/null"
    )
    if brew_check.returncode == 124:
        timed_out.append("brew")
    if brew_check.returncode == 0 and brew_check.stdout.strip():
        parts.append(f"[Tier 3 - Homebrew]\n{brew_check.stdout}")

    if not parts:
        timeout_note = (
            f"\nNote: timed out querying {', '.join(timed_out)}." if timed_out else ""
        )
        return (
            f"No results for '{package}' in ujust, flatpak, or brew.\n"
            "Consider distrobox or rpm-ostree (last resort)."
            f"{timeout_note}"
        )
    timeout_note = (
        f"\n\nNote: timed out querying {', '.join(timed_out)}." if timed_out else ""
    )
    return "\n\n".join(parts) + timeout_note + f"\n\n{INSTALL_POLICY}"


def list_packages(
    source: Literal["flatpak", "brew", "rpm-ostree"] | None = None,
) -> str:
    """List installed packages by source, or all sources if omitted."""
    parts: list[str] = []
    sources = [source] if source else ["flatpak", "brew", "rpm-ostree"]

    if "flatpak" in sources:
        result = _run_search_command(
            "flatpak list --app --columns=name,application,version 2>/dev/null"
        )
        if result.returncode == 0 and result.stdout.strip():
            parts.append(f"=== Flatpak ===\n{result.stdout}")

    if "brew" in sources:
        result = _run_search_command("HOMEBREW_NO_AUTO_UPDATE=1 brew list 2>/dev/null")
        if result.returncode == 0 and result.stdout.strip():
            parts.append(f"=== Homebrew ===\n{result.stdout}")

    if "rpm-ostree" in sources:
        result = _run_search_command("rpm-ostree status --json 2>/dev/null")
        if result.returncode == 0:
            layered = "No layered packages"
            try:
                data = json.loads(result.stdout)
                deployments = data.get("deployments", [])
                if deployments:
                    requested = deployments[0].get("requested-packages", [])
                    if requested:
                        layered = "\n".join(str(pkg_name) for pkg_name in requested)
            except json.JSONDecodeError:
                layered = "Could not parse rpm-ostree status JSON"
            parts.append(f"=== rpm-ostree (layered) ===\n{layered}")

    return "\n\n".join(parts) if parts else "No packages found."


def update_packages(source: Literal["system", "flatpak", "brew"] | None = None) -> str:
    """Update packages by source, or run full system update if omitted."""
    if source in (None, "system"):
        result = run_audited(
            "ujust update", tool="update_packages", args={"source": "system"}
        )
        return f"System update:\n{result.stdout}"
    if source == "flatpak":
        result = run_audited(
            "flatpak update -y", tool="update_packages", args={"source": "flatpak"}
        )
        return f"Flatpak update:\n{result.stdout}"
    if source == "brew":
        result = run_audited(
            "brew upgrade", tool="update_packages", args={"source": "brew"}
        )
        return f"Brew update:\n{result.stdout}"
    raise ToolError(
        f"Unknown source '{source}'. Supported: flatpak, brew, system, all."
    )
