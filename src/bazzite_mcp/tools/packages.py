import shlex

from bazzite_mcp.runner import run_audited, run_command


INSTALL_POLICY = """Bazzite 6-tier install hierarchy (official docs.bazzite.gg):
1. ujust - check ujust --summary for setup/install commands first
2. flatpak - primary method for GUI apps (via Flathub)
3. brew - CLI/TUI tools only (no GUI apps)
4. distrobox - for packages from other distro repos (apt, pacman, etc.)
5. AppImage - portable apps from trusted sources only
6. rpm-ostree - last resort. Can freeze updates, block rebasing, cause conflicts."""


def install_package(package: str, method: str | None = None) -> str:
    """Install package following Bazzite hierarchy or explicit method."""
    if method:
        return _install_with_method(package, method)

    pkg = shlex.quote(package)
    ujust_check = run_command(
        f"ujust --summary 2>/dev/null | grep -iE {shlex.quote(f'install.*{package}|setup.*{package}')}"
    )
    if ujust_check.returncode == 0 and ujust_check.stdout.strip():
        commands = ujust_check.stdout.strip().split("\n")
        return (
            f"Found ujust command(s) for '{package}':\n"
            + "\n".join(f"  ujust {cmd.strip()}" for cmd in commands)
            + f"\n\nRun with: ujust_run tool\n\n{INSTALL_POLICY}"
        )

    flatpak_check = run_command(f"flatpak search {pkg} 2>/dev/null")
    if flatpak_check.returncode == 0 and flatpak_check.stdout.strip():
        return (
            f"Flatpak results for '{package}':\n{flatpak_check.stdout}\n\n"
            f"Recommended: flatpak install flathub <app-id>\n\n{INSTALL_POLICY}"
        )

    brew_check = run_command(f"brew search {pkg} 2>/dev/null")
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
        return f"Unknown method '{method}'. Supported: {', '.join(method_commands.keys())}"

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
        return f"Installation failed (exit {result.returncode}):\n{output}"
    return f"Installed '{package}' via {method}:\n{output}"


def remove_package(package: str, method: str) -> str:
    """Remove package via original install method."""
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
        return f"Unknown method '{method}'. Supported: {', '.join(method_commands.keys())}"

    result = run_audited(
        method_commands[method],
        tool="remove_package",
        args={"package": package, "method": method},
        rollback=reinstall_commands.get(method),
    )
    output = result.stdout
    if result.returncode != 0:
        output = f"Removal failed (exit {result.returncode}):\n{output}\n{result.stderr}"
    return output


def search_package(package: str) -> str:
    """Search package across ujust, flatpak, brew."""
    parts: list[str] = []

    pkg = shlex.quote(package)
    ujust_check = run_command(f"ujust --summary 2>/dev/null | grep -i {pkg}")
    if ujust_check.returncode == 0 and ujust_check.stdout.strip():
        parts.append(f"[Tier 1 - ujust]\n{ujust_check.stdout}")

    flatpak_check = run_command(f"flatpak search {pkg} 2>/dev/null")
    if flatpak_check.returncode == 0 and flatpak_check.stdout.strip():
        parts.append(f"[Tier 2 - Flatpak]\n{flatpak_check.stdout}")

    brew_check = run_command(f"brew search {pkg} 2>/dev/null")
    if brew_check.returncode == 0 and brew_check.stdout.strip():
        parts.append(f"[Tier 3 - Homebrew]\n{brew_check.stdout}")

    if not parts:
        return (
            f"No results for '{package}' in ujust, flatpak, or brew.\n"
            "Consider distrobox or rpm-ostree (last resort)."
        )
    return "\n\n".join(parts) + f"\n\n{INSTALL_POLICY}"


def list_packages(source: str | None = None) -> str:
    """List installed packages by source or all."""
    parts: list[str] = []
    sources = [source] if source else ["flatpak", "brew", "rpm-ostree"]

    if "flatpak" in sources:
        result = run_command("flatpak list --app --columns=name,application,version 2>/dev/null")
        if result.returncode == 0 and result.stdout.strip():
            parts.append(f"=== Flatpak ===\n{result.stdout}")

    if "brew" in sources:
        result = run_command("brew list 2>/dev/null")
        if result.returncode == 0 and result.stdout.strip():
            parts.append(f"=== Homebrew ===\n{result.stdout}")

    if "rpm-ostree" in sources:
        result = run_command(
            "rpm-ostree status --json 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); pkgs=d['deployments'][0].get('requested-packages',[]); print(chr(10).join(pkgs) if pkgs else 'No layered packages')\""
        )
        if result.returncode == 0:
            parts.append(f"=== rpm-ostree (layered) ===\n{result.stdout}")

    return "\n\n".join(parts) if parts else "No packages found."


def update_packages(source: str | None = None) -> str:
    """Update packages by source."""
    if source in (None, "system"):
        result = run_audited("ujust update", tool="update_packages", args={"source": "system"})
        return f"System update:\n{result.stdout}"
    if source == "flatpak":
        result = run_audited("flatpak update -y", tool="update_packages", args={"source": "flatpak"})
        return f"Flatpak update:\n{result.stdout}"
    if source == "brew":
        result = run_audited("brew upgrade", tool="update_packages", args={"source": "brew"})
        return f"Brew update:\n{result.stdout}"
    return f"Unknown source '{source}'. Supported: flatpak, brew, system, all."
