from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_command


def _first_matching_line(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle.lower() in line.lower():
            return line.strip()
    return ""


def _system_info_basic() -> str:
    """Get OS, kernel, desktop, and hardware summary."""
    os_result = run_command("cat /etc/os-release")
    os_lines = [
        line
        for line in os_result.stdout.splitlines()
        if line.startswith(("NAME=", "VERSION=", "VARIANT="))
    ]
    os_summary = "\n".join(os_lines[:5]) if os_lines else os_result.stdout

    kernel_result = run_command("uname -r")
    desktop_result = run_command("echo $XDG_CURRENT_DESKTOP")
    session_result = run_command("echo $XDG_SESSION_TYPE")

    lscpu_result = run_command("lscpu")
    cpu_model = _first_matching_line(lscpu_result.stdout, "model name")

    lspci_result = run_command("lspci")
    gpu_lines = [
        line
        for line in lspci_result.stdout.splitlines()
        if "vga" in line.lower() or "3d" in line.lower()
    ]
    gpu_summary = "\n".join(gpu_lines[:2]) if gpu_lines else lspci_result.stdout

    free_result = run_command("free -h")
    mem_line = _first_matching_line(free_result.stdout, "Mem:")
    mem_total = mem_line.split()[1] if mem_line else free_result.stdout

    hostname_result = run_command("hostname")

    return "\n".join(
        [
            f"OS: {os_summary}",
            f"Kernel: {kernel_result.stdout}",
            f"Desktop: {desktop_result.stdout}",
            f"Session: {session_result.stdout}",
            f"CPU: {cpu_model}",
            f"GPU: {gpu_summary}",
            f"RAM: {mem_total}",
            f"Hostname: {hostname_result.stdout}",
        ]
    )


def _hardware_info() -> str:
    """Get a broader hardware report."""
    lscpu_result = run_command("lscpu")
    cpu_output = "\n".join(lscpu_result.stdout.splitlines()[:20])

    lspci_result = run_command("lspci -v")
    lspci_lines = lspci_result.stdout.splitlines()
    gpu_output = ""
    for index, line in enumerate(lspci_lines):
        lowered = line.lower()
        if "vga" in lowered or "3d" in lowered:
            gpu_output = "\n".join(lspci_lines[index : index + 11])
            break
    if not gpu_output:
        gpu_output = lspci_result.stdout

    memory_result = run_command("free -h")
    block_result = run_command("lsblk -o NAME,SIZE,TYPE,MOUNTPOINT")
    sensors_result = run_command("sensors")
    sensors_output = (
        sensors_result.stdout
        if sensors_result.returncode == 0
        else "sensors not available"
    )

    parts: list[str] = [
        f"=== CPU ===\n{cpu_output}",
        f"=== GPU ===\n{gpu_output}",
        f"=== Memory ===\n{memory_result.stdout}",
        f"=== Block Devices ===\n{block_result.stdout}",
        f"=== Sensors ===\n{sensors_output}",
    ]
    return "\n\n".join(parts)


def _fmt_size(mb: int) -> str:
    """Format megabytes as a human-readable string."""
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb} MB"


def _pct(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{part / total * 100:.1f}%"


def _bar(part: int, total: int, width: int = 30) -> str:
    """Render a simple ASCII progress bar."""
    if total <= 0:
        return "[" + " " * width + "]"
    filled = round(part / total * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def storage_diagnostics() -> str:
    """Capture full storage breakdown with optimization suggestions."""
    lines: list[str] = []

    # ── 1. Parse df for all real partitions ──
    df_result = run_command(
        "df --block-size=1M --output=source,size,used,avail,pcent,target "
        "-x tmpfs -x devtmpfs -x squashfs"
    )

    partitions: dict[str, dict] = {}
    boot_mb = 0
    if df_result.returncode == 0:
        for line in df_result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue
            source = parts[0]
            try:
                size, used, avail = int(parts[1]), int(parts[2]), int(parts[3])
            except ValueError:
                continue
            target = parts[5]
            if target in ("/boot", "/boot/efi"):
                boot_mb += used
                continue
            if source not in partitions:
                partitions[source] = {
                    "size": size,
                    "used": used,
                    "avail": avail,
                    "target": target,
                }

    main = max(partitions.values(), key=lambda p: p["size"]) if partitions else None
    total_mb = main["size"] if main else 1
    used_mb = main["used"] if main else 0
    free_mb = main["avail"] if main else 0

    # ── 2. Total home usage ──
    home_total_result = run_command("du -sm $HOME", timeout=90)
    home_total_mb = 0
    if home_total_result.stdout:
        try:
            home_total_mb = int(home_total_result.stdout.split("\t")[0])
        except (ValueError, IndexError):
            pass

    system_mb = max(0, used_mb - home_total_mb)

    # ── 3. Home directory breakdown ──
    home_dirs = [
        (".local/share/Steam", "Steam"),
        (".local/share/lutris", "Lutris"),
        ("Games", "Games"),
        ("Backups", "Backups"),
        (".var", "Flatpak Data"),
        (".cache", "Cache"),
        (".local/share/containers", "Containers"),
        (".config", "Config"),
        ("Downloads", "Downloads"),
        ("Documents", "Documents"),
        ("Pictures", "Pictures"),
        ("Videos", "Videos"),
        ("Music", "Music"),
        (".local/share/Trash", "Trash"),
    ]

    paths_str = " ".join(f"$HOME/{suffix}" for suffix, _ in home_dirs)
    du_result = run_command(f"du -sm {paths_str}", timeout=60)

    dir_sizes: list[tuple[str, int]] = []
    if du_result.stdout:
        for line in du_result.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                try:
                    size_mb = int(parts[0])
                except ValueError:
                    continue
                path = parts[1].rstrip("/")
                for suffix, label in home_dirs:
                    if path.endswith("/" + suffix):
                        dir_sizes.append((label, size_mb))
                        break

    dir_sizes.sort(key=lambda x: x[1], reverse=True)
    accounted_home_mb = sum(mb for _, mb in dir_sizes)
    other_home_mb = max(0, home_total_mb - accounted_home_mb)

    # ── Format: Drive overview ──
    lines.append(
        f"DRIVE TOTAL: {_fmt_size(total_mb)}  "
        f"USED: {_fmt_size(used_mb)} ({_pct(used_mb, total_mb)})  "
        f"FREE: {_fmt_size(free_mb)}"
    )
    lines.append(f"  {_bar(used_mb, total_mb, 50)}")
    lines.append("")

    # ── Format: Top-level breakdown (System vs Home vs Free) ──
    lines.append("USAGE BREAKDOWN")
    lines.append(f"  System/OS    {_fmt_size(system_mb):>10}  {_pct(system_mb, total_mb):>6}")
    lines.append(f"  Home         {_fmt_size(home_total_mb):>10}  {_pct(home_total_mb, total_mb):>6}")
    if boot_mb > 0:
        lines.append(f"  Boot         {_fmt_size(boot_mb):>10}  {_pct(boot_mb, total_mb):>6}")
    lines.append(f"  Free         {_fmt_size(free_mb):>10}  {_pct(free_mb, total_mb):>6}")
    check_total = system_mb + home_total_mb + boot_mb + free_mb
    lines.append(f"               {'─' * 10}")
    lines.append(f"  Accounted    {_fmt_size(check_total):>10}  {_pct(check_total, total_mb):>6}")
    lines.append("")

    # ── Format: Home breakdown ──
    lines.append(f"HOME BREAKDOWN ({_fmt_size(home_total_mb)} total)")
    label_width = max((len(label) for label, _ in dir_sizes), default=12)
    label_width = max(label_width, len("Other"))
    for label, mb in dir_sizes:
        if mb >= 1:
            lines.append(
                f"  {label:<{label_width}}  {_fmt_size(mb):>10}  "
                f"{_pct(mb, home_total_mb):>6}  {_bar(mb, home_total_mb, 20)}"
            )
    if other_home_mb > 0:
        lines.append(
            f"  {'Other':<{label_width}}  {_fmt_size(other_home_mb):>10}  "
            f"{_pct(other_home_mb, home_total_mb):>6}  {_bar(other_home_mb, home_total_mb, 20)}"
        )
    lines.append("")

    # ── Flatpak sizes ──
    flatpak_result = run_command("flatpak list --columns=name,size")
    if flatpak_result.returncode == 0 and flatpak_result.stdout.strip():
        lines.append("FLATPAK APPS (installed size)")
        for fl in flatpak_result.stdout.strip().splitlines():
            lines.append(f"  {fl}")
        lines.append("")

    # ── Podman ──
    podman_result = run_command("podman system df")
    if podman_result.returncode == 0 and podman_result.stdout.strip():
        lines.append("PODMAN STORAGE")
        for pl in podman_result.stdout.strip().splitlines():
            lines.append(f"  {pl}")
        lines.append("")

    # ── Journal logs ──
    journal_result = run_command("journalctl --disk-usage")
    if journal_result.returncode == 0:
        lines.append(f"JOURNAL LOGS: {journal_result.stdout.strip()}")
        lines.append("")

    # ── Brew cache ──
    brew_cache_mb = 0
    brew_result = run_command("brew --cache")
    if brew_result.returncode == 0 and brew_result.stdout.strip():
        brew_cache_path = brew_result.stdout.strip()
        brew_du = run_command(
            f"du -sm {shlex.quote(brew_cache_path)}", timeout=30
        )
        if brew_du.returncode == 0:
            try:
                brew_cache_mb = int(brew_du.stdout.split("\t")[0])
            except (ValueError, IndexError):
                pass
    if brew_cache_mb > 0:
        lines.append(f"BREW CACHE: {_fmt_size(brew_cache_mb)}")
        lines.append("")

    return "\n".join(lines)


def _snapshot_list() -> str:
    """List btrfs snapshots of the home directory."""
    result = run_command(
        "snapper -c home list --columns number,date,description,cleanup"
    )
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def _snapshot_status() -> str:
    """Show snapshot system status: retention policy, timer state, snapshot count."""
    lines: list[str] = []

    config_result = run_command("snapper -c home get-config")
    if config_result.returncode == 0:
        lines.append("RETENTION POLICY")
        for cfg_line in config_result.stdout.splitlines():
            if "TIMELINE_LIMIT" in cfg_line or "SPACE_LIMIT" in cfg_line:
                lines.append(f"  {cfg_line.strip()}")
        lines.append("")

    timeline_result = run_command("systemctl is-active snapper-timeline.timer")
    cleanup_result = run_command("systemctl is-active snapper-cleanup.timer")
    lines.append("TIMERS")
    lines.append(f"  snapper-timeline: {timeline_result.stdout.strip()}")
    lines.append(f"  snapper-cleanup:  {cleanup_result.stdout.strip()}")
    lines.append("")

    list_result = run_command(
        "snapper -c home list --columns number,date,cleanup"
    )
    if list_result.returncode == 0:
        count = sum(
            1
            for line in list_result.stdout.splitlines()
            if line.strip() and not line.startswith("#") and "─" not in line
        )
        lines.append(f"SNAPSHOTS: {count} total")

    return "\n".join(lines)


def _snapshot_diff(snapshot_id: int) -> str:
    """Show what files changed between a snapshot and the current state."""
    safe_id = max(1, int(snapshot_id))
    result = run_command(f"snapper -c home status {safe_id}..0")
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def system_doctor() -> str:
    """Run security and health checks with PASS/WARN/FAIL assessments."""
    lines: list[str] = []

    # ── SECURITY ──
    lines.append("SECURITY")

    # 1. Firewall zone
    fw_result = run_command("firewall-cmd --get-default-zone")
    if fw_result.returncode == 0:
        zone = fw_result.stdout.strip()
        if zone == "public":
            lines.append(f"  PASS  Firewall default zone: {zone}")
        else:
            lines.append(f"  FAIL  Firewall default zone: {zone} (expected: public)")
    else:
        lines.append("  FAIL  Firewall: could not query")

    # 2. No unexpected open services
    svc_result = run_command("firewall-cmd --list-services")
    if svc_result.returncode == 0:
        services = set(svc_result.stdout.strip().split())
        expected = {"dhcpv6-client"}
        unexpected = services - expected
        if not unexpected:
            lines.append(f"  PASS  Firewall services: {', '.join(sorted(services)) or 'none'}")
        else:
            lines.append(f"  WARN  Firewall unexpected services: {', '.join(sorted(unexpected))}")

    # 3. DNS: over-TLS + LLMNR/mDNS
    dns_parts: list[str] = []
    dns_ok = True
    resolve_result = run_command("systemctl is-active systemd-resolved")
    if resolve_result.stdout.strip() == "active":
        resolvectl = run_command("resolvectl status")
        if resolvectl.returncode == 0:
            if "DNSOverTLS" in resolvectl.stdout and (
                "+DNSOverTLS" in resolvectl.stdout
                or "DNSOverTLS setting: yes" in resolvectl.stdout
            ):
                dns_parts.append("DoTLS active")
            elif "DNS over TLS" in resolvectl.stdout:
                dns_parts.append("DoTLS active")
            else:
                cfg_result = run_command(
                    "cat /etc/systemd/resolved.conf.d/20-encrypted-dns.conf"
                )
                if cfg_result.returncode == 0 and "DNSOverTLS=yes" in cfg_result.stdout:
                    dns_parts.append("DoTLS configured")
                else:
                    dns_parts.append("DoTLS not configured")
                    dns_ok = False

        llmnr_result = run_command(
            "cat /etc/systemd/resolved.conf.d/10-network-hardening.conf"
        )
        if llmnr_result.returncode == 0:
            content = llmnr_result.stdout
            if "LLMNR=no" in content and "MulticastDNS=no" in content:
                dns_parts.append("LLMNR/mDNS disabled")
            else:
                dns_parts.append("LLMNR/mDNS not fully disabled")
                dns_ok = False
        else:
            dns_parts.append("LLMNR/mDNS config missing")
            dns_ok = False
    else:
        dns_parts.append("systemd-resolved not active")
        dns_ok = False

    status = "PASS" if dns_ok else "WARN"
    lines.append(f"  {status}  DNS: {', '.join(dns_parts)}")

    # 4. Sysctl hardening
    sysctl_checks = {
        "kernel.kptr_restrict": "1",
        "net.ipv4.conf.all.rp_filter": "1",
        "net.ipv6.conf.all.accept_redirects": "0",
    }
    sysctl_failures: list[str] = []
    for key, expected_val in sysctl_checks.items():
        proc_path = f"/proc/sys/{key.replace('.', '/')}"
        sysctl_result = run_command(f"cat {proc_path}")
        if sysctl_result.returncode == 0:
            actual = sysctl_result.stdout.strip()
            if actual != expected_val:
                sysctl_failures.append(f"{key}={actual}")
        else:
            sysctl_failures.append(f"{key}=unreadable")

    if not sysctl_failures:
        lines.append("  PASS  Sysctl: kptr_restrict, rp_filter, ICMP redirects")
    else:
        lines.append(f"  FAIL  Sysctl drift: {', '.join(sysctl_failures)}")

    lines.append("")

    # ── HEALTH ──
    lines.append("HEALTH")

    # Failed systemd units
    failed_result = run_command("systemctl --failed --no-legend")
    if failed_result.returncode == 0:
        failed_lines = [
            l for l in failed_result.stdout.strip().splitlines() if l.strip()
        ]
        if not failed_lines:
            lines.append("  PASS  No failed systemd units")
        else:
            units = [
                p for l in failed_lines
                for p in l.split()
                if p.endswith(".service") or p.endswith(".socket") or p.endswith(".timer")
            ]
            lines.append(f"  WARN  Failed units: {', '.join(units)}")
    else:
        lines.append("  PASS  No failed systemd units")

    # Disk usage
    df_result = run_command(
        "df --block-size=1M --output=size,used,avail,pcent,target "
        "-x tmpfs -x devtmpfs -x squashfs"
    )
    if df_result.returncode == 0:
        best_size = 0
        pct = 0
        free_mb = 0
        for line in df_result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                try:
                    size = int(parts[0])
                except ValueError:
                    continue
                if size > best_size:
                    best_size = size
                    free_mb = int(parts[2])
                    pct = round(int(parts[1]) / size * 100)
        status = "PASS" if pct < 80 else ("WARN" if pct < 90 else "FAIL")
        lines.append(f"  {status}  Disk: {pct}% used ({_fmt_size(free_mb)} free)")

    # Podman reclaimable
    podman_result = run_command("podman system df")
    if podman_result.returncode == 0:
        for pl in podman_result.stdout.splitlines():
            if "images" in pl.lower():
                parts = pl.split()
                for i, p in enumerate(parts):
                    if "reclaimable" in p.lower() or (
                        "(" in p and "%" in p
                    ):
                        reclaim_size = parts[i - 1] if i > 0 else "0B"
                        if reclaim_size != "0B":
                            lines.append(
                                f"  WARN  Podman: {reclaim_size} reclaimable images"
                            )
                        else:
                            lines.append("  PASS  Podman: no reclaimable images")
                        break
                break

    # Snapshots
    snap_timer = run_command("systemctl is-active snapper-timeline.timer")
    if snap_timer.stdout.strip() == "active":
        snap_list = run_command(
            "snapper -c home list --columns number"
        )
        if snap_list.returncode == 0:
            count = sum(
                1
                for line in snap_list.stdout.splitlines()
                if line.strip() and not line.startswith("#") and "─" not in line
            )
            lines.append(f"  PASS  Snapshots: timer active, {count} snapshots")
        else:
            lines.append("  PASS  Snapshots: timer active")
    else:
        lines.append("  FAIL  Snapshots: timeline timer not active")

    # Journal size
    journal_result = run_command("journalctl --disk-usage")
    if journal_result.returncode == 0:
        journal_text = journal_result.stdout.strip()
        if "G" in journal_text.split("up")[-1] if "up" in journal_text else "":
            lines.append(f"  WARN  {journal_text}")
        else:
            lines.append(f"  PASS  {journal_text}")

    # Service preferences (informational, not security)
    for svc_name, label in [("avahi-daemon", "Avahi"), ("cups.socket", "CUPS")]:
        svc_check = run_command(f"systemctl is-enabled {svc_name}")
        state = svc_check.stdout.strip()
        if state == "disabled":
            lines.append(f"  INFO  {label}: disabled")
        elif state == "enabled":
            lines.append(f"  INFO  {label}: enabled")

    return "\n".join(lines)


# --- Dispatchers ---


def system_info(detail: Literal["basic", "full"] = "basic") -> str:
    """Get system info: basic (OS/kernel/GPU summary) or full (CPU/GPU/memory/sensors/disks)."""
    if detail == "full":
        return _hardware_info()
    return _system_info_basic()


def manage_snapshots(
    action: Literal["list", "status", "diff"],
    snapshot_id: int | None = None,
) -> str:
    """Manage btrfs home snapshots: list, check status, or diff against current state."""
    if action == "list":
        return _snapshot_list()
    if action == "status":
        return _snapshot_status()
    if action == "diff":
        if snapshot_id is None:
            raise ToolError("'snapshot_id' is required for action='diff'.")
        return _snapshot_diff(snapshot_id)
    raise ToolError(f"Unknown action '{action}'.")
