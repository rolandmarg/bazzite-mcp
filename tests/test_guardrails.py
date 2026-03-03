import pytest

from bazzite_mcp.guardrails import GuardrailError, check_command


def test_blocks_rm_rf_root() -> None:
    with pytest.raises(GuardrailError, match="destructive"):
        check_command("rm -rf /")


def test_blocks_mkfs() -> None:
    with pytest.raises(GuardrailError, match="destructive"):
        check_command("mkfs.ext4 /dev/sda1")


def test_blocks_rpm_ostree_reset() -> None:
    with pytest.raises(GuardrailError, match="destructive"):
        check_command("rpm-ostree reset")


def test_warns_rpm_ostree_install() -> None:
    result = check_command("rpm-ostree install htop")
    assert result.warning is not None
    assert "last resort" in result.warning.lower()


def test_allows_flatpak_install() -> None:
    result = check_command("flatpak install flathub org.mozilla.firefox")
    assert result.warning is None
    assert result.allowed is True


def test_blocks_long_hostname() -> None:
    with pytest.raises(GuardrailError, match="hostname"):
        check_command("hostnamectl set-hostname this-hostname-is-way-too-long-for-distrobox")


def test_allows_short_hostname() -> None:
    result = check_command("hostnamectl set-hostname mypc")
    assert result.allowed is True
