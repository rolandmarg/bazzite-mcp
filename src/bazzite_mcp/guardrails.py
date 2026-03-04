from __future__ import annotations

import re
import shlex
from dataclasses import dataclass


class GuardrailError(Exception):
    pass


@dataclass
class CheckResult:
    allowed: bool
    warning: str | None = None


# Commands allowed as the first word of a shell command.
# Everything else is blocked by default.
ALLOWED_COMMAND_PREFIXES = frozenset(
    {
        "brew",
        "cat",
        "df",
        "distrobox",
        "distrobox-export",
        "echo",
        "false",
        "firewall-cmd",
        "flatpak",
        "free",
        "gdbus",
        "gh",
        "git",
        "gnome-randr",
        "grep",
        "head",
        "hostnamectl",
        "hostname",
        "ip",
        "journalctl",
        "lsblk",
        "lscpu",
        "lspci",
        "magick",
        "mkdir",
        "nmcli",
        "pactl",
        "pkexec",
        "podman",
        "powerprofilesctl",
        "ps",
        "python3",
        "qdbus",
        "rpm-ostree",
        "sensors",
        "spectacle",
        "sudo",
        "systemctl",
        "gsettings",
        "tailscale",
        "true",
        "uname",
        "ujust",
        "vulkaninfo",
        "waydroid",
        "xrandr",
        "ydotool",
    }
)

BLOCKED_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+.*)?/\s*$", "destructive filesystem operation"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/", "destructive filesystem operation"),
    (r"\bmkfs\b", "destructive filesystem operation"),
    (r"\brpm-ostree\s+reset\b", "destructive: removes ALL layered packages"),
    (
        r"\brpm-ostree\s+rebase\b.*(?:gnome|kde|plasma|sway|hyprland|cosmic)",
        "Do NOT rebase to switch desktop environments. Backup and reinstall instead.",
    ),
    (r"\bdd\s+.*of=/dev/", "destructive disk write"),
    # Shell injection vectors
    (r"\beval\b", "eval is blocked for safety"),
    (r"\bbash\s+-c\b", "bash -c is blocked for safety"),
    (r"\bsh\s+-c\b", "sh -c is blocked for safety"),
    (r"\|\s*bash\b", "piping to bash is blocked for safety"),
    (r"\|\s*sh\b", "piping to sh is blocked for safety"),
    (r"\bbase64\b.*\|\s*(bash|sh)\b", "base64 decode to shell is blocked"),
    # Destructive system operations
    (r"\bshred\b", "destructive file operation"),
    (r"\bwipefs\b", "destructive disk operation"),
    (r"\bsystemctl\s+(mask|unmask)\b", "masking services is blocked for safety"),
    (r"\bchmod\s+[0-7]*777\b", "world-writable permissions are blocked"),
    (r"\bchown\s+root\b", "changing ownership to root is blocked"),
    # Fork bombs and resource exhaustion
    (r":\(\)\s*\{", "fork bomb detected"),
    (r"\bwhile\s+true\b.*\bdone\b", "infinite loop detected"),
    (r"[;|`]|&&|\|\|", "shell metacharacters (;, |, &&, ||, `) are blocked"),
    (r"\$\(", "command substitution $() is blocked"),
    # Privilege escalation via path
    (r"/usr/s?bin/rm\b", "use rm without full path"),
    # Network exfiltration
    (r"\bcurl\b", "curl is blocked; use httpx in Python instead"),
    (r"\bwget\b", "wget is blocked; use httpx in Python instead"),
    (r"\bnc\b", "netcat is blocked for safety"),
    (r"\bncat\b", "ncat is blocked for safety"),
    # Dangerous redirects
    (r">\s*/etc/", "writing to /etc is blocked"),
    (r"(?<![0-9])>>?\s*/dev/|\b1>>?\s*/dev/", "writing to /dev is blocked"),
]

WARN_PATTERNS = [
    (
        r"\brpm-ostree\s+install\b",
        "rpm-ostree is a LAST RESORT on Bazzite. It can freeze updates, block rebasing, and cause dependency conflicts. Prefer: ujust > flatpak > brew > distrobox > AppImage.",
    ),
]

HOSTNAME_RE = re.compile(r"\bhostnamectl\s+set-hostname\s+(\S+)")


def _extract_command_prefix(command: str) -> str | None:
    """Extract the first command from a shell string for allowlist checking."""
    # Strip leading env assignments (FOO=bar cmd ...)
    stripped = command.strip()
    while re.match(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
        stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
    try:
        parts = shlex.split(stripped)
    except ValueError:
        return None
    if not parts:
        return None
    # Get the basename of the command (in case of /usr/bin/foo)
    cmd = parts[0].rsplit("/", 1)[-1]
    return cmd


def check_command(command: str) -> CheckResult:
    # Check blocked patterns first (these override everything)
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            raise GuardrailError(f"Blocked: {reason}")

    # Check command allowlist
    prefix = _extract_command_prefix(command)
    if prefix and prefix not in ALLOWED_COMMAND_PREFIXES:
        raise GuardrailError(
            f"Blocked: command '{prefix}' is not in the allowed command list"
        )

    hostname_match = HOSTNAME_RE.search(command)
    if hostname_match:
        hostname = hostname_match.group(1).strip("'\"")
        if len(hostname) > 20:
            raise GuardrailError(
                f"Blocked: hostname '{hostname}' exceeds 20 characters (breaks Distrobox)"
            )

    for pattern, warning in WARN_PATTERNS:
        if re.search(pattern, command):
            return CheckResult(allowed=True, warning=warning)

    return CheckResult(allowed=True)
