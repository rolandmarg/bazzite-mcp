import re
from dataclasses import dataclass


class GuardrailError(Exception):
    pass


@dataclass
class CheckResult:
    allowed: bool
    warning: str | None = None


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
    # Privilege escalation via path
    (r"/usr/s?bin/rm\b", "use rm without full path"),
]

WARN_PATTERNS = [
    (
        r"\brpm-ostree\s+install\b",
        "rpm-ostree is a LAST RESORT on Bazzite. It can freeze updates, block rebasing, and cause dependency conflicts. Prefer: ujust > flatpak > brew > distrobox > AppImage.",
    ),
]

HOSTNAME_RE = re.compile(r"\bhostnamectl\s+set-hostname\s+(\S+)")


def check_command(command: str) -> CheckResult:
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            raise GuardrailError(f"Blocked: {reason}")

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
