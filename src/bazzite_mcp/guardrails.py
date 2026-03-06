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


# Commands allowed as the first word of a command.
# Everything else is blocked by default.
ALLOWED_COMMAND_PREFIXES = frozenset(
    {
        "brew",
        "cat",
        "df",
        "du",
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
        "kscreen-doctor",
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
        "resolvectl",
        "rpm-ostree",
        "sensors",
        "snapper",
        "spectacle",
        "sudo",
        "systemctl",
        "gsettings",
        "tailscale",
        "true",
        "uname",
        "ujust",
        "vulkaninfo",
        "virsh",
        "virt-install",
        "waydroid",
        "xrandr",
        "ydotool",
    }
)

SHELL_SYNTAX_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+.*)?/\s*$", "destructive filesystem operation"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/", "destructive filesystem operation"),
    (r"\bmkfs\b", "destructive filesystem operation"),
    (r"\bdd\s+.*of=/dev/", "destructive disk write"),
    (r"\bshred\b", "destructive file operation"),
    (r"\bwipefs\b", "destructive disk operation"),
    (r"\bchmod\s+[0-7]*777\b", "world-writable permissions are blocked"),
    (r"\bchown\s+root\b", "changing ownership to root is blocked"),
    (r"\beval\b", "eval is blocked for safety"),
    (r"\bbash\s+-c\b", "bash -c is blocked for safety"),
    (r"\bsh\s+-c\b", "sh -c is blocked for safety"),
    (r"\|\s*bash\b", "piping to bash is blocked for safety"),
    (r"\|\s*sh\b", "piping to sh is blocked for safety"),
    (r"\bbase64\b.*\|\s*(bash|sh)\b", "base64 decode to shell is blocked"),
    (r":\(\)\s*\{", "fork bomb detected"),
    (r"\bwhile\s+true\b.*\bdone\b", "infinite loop detected"),
    (r";", "semicolons are blocked for safety"),
    (r"&&", "command chaining (&&) is blocked for safety"),
    (r"\|\|", "command chaining (||) is blocked for safety"),
    (r"`", "backtick substitution is blocked for safety"),
    (r"(?<!\d)\|(?!\|)", "pipes are blocked for safety"),
    (r"\$\(", "command substitution $() is blocked"),
    (r">\s*/etc/", "writing to /etc is blocked"),
    (r"(?<![0-9])>>?\s*/dev/|\b1>>?\s*/dev/", "writing to /dev is blocked"),
]

_BLOCKED_BINARIES = frozenset(
    {
        "curl",
        "wget",
        "nc",
        "ncat",
        "eval",
        "bash",
        "sh",
    }
)

_BLOCKED_BINARY_REASONS = {
    "curl": "'curl' is not allowed; use httpx in Python instead",
    "wget": "'wget' is not allowed; use httpx in Python instead",
    "nc": "'nc' is not allowed; netcat is blocked for safety",
    "ncat": "'ncat' is not allowed; ncat is blocked for safety",
    "eval": "'eval' is not allowed; eval is blocked for safety",
    "bash": "'bash' is not allowed; bash -c is blocked for safety",
    "sh": "'sh' is not allowed; sh -c is blocked for safety",
}

RPM_OSTREE_WARNING = (
    "rpm-ostree is a LAST RESORT on Bazzite. It can freeze updates, block "
    "rebasing, and cause dependency conflicts. Prefer: ujust > flatpak > brew "
    "> distrobox > AppImage."
)


def check_command(command: str) -> CheckResult:
    """Validate a string command before tokenizing it to argv."""
    for pattern, reason in SHELL_SYNTAX_PATTERNS:
        if re.search(pattern, command):
            raise GuardrailError(f"Blocked: {reason}")

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise GuardrailError(f"Blocked: invalid command syntax: {exc}") from exc

    return check_argv(argv)


def check_argv(argv: list[str]) -> CheckResult:
    """Validate a command given as an argv list."""
    if not argv:
        raise GuardrailError("Blocked: empty command")

    binary = argv[0].rsplit("/", 1)[-1]
    if binary in _BLOCKED_BINARIES:
        raise GuardrailError(f"Blocked: {_BLOCKED_BINARY_REASONS[binary]}")

    if binary not in ALLOWED_COMMAND_PREFIXES:
        raise GuardrailError(
            f"Blocked: command '{binary}' is not in the allowed command list"
        )

    args = argv[1:]

    if binary == "systemctl" and any(a in ("mask", "unmask") for a in args):
        raise GuardrailError("Blocked: masking services is blocked for safety")

    if binary == "rpm-ostree":
        if "reset" in args:
            raise GuardrailError("Blocked: destructive: removes ALL layered packages")
        if "rebase" in args:
            rest = " ".join(args)
            if re.search(r"gnome|kde|plasma|sway|hyprland|cosmic", rest):
                raise GuardrailError(
                    "Blocked: Do NOT rebase to switch desktop environments."
                )
        if "install" in args:
            return CheckResult(allowed=True, warning=RPM_OSTREE_WARNING)

    if binary == "hostnamectl" and "set-hostname" in args:
        idx = args.index("set-hostname")
        if idx + 1 < len(args):
            hostname = args[idx + 1].strip("'\"")
            if len(hostname) > 20:
                raise GuardrailError(
                    f"Blocked: hostname '{hostname}' exceeds 20 characters (breaks Distrobox)"
                )

    return CheckResult(allowed=True)
