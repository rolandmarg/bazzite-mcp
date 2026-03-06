from __future__ import annotations

from pathlib import Path

from bazzite_mcp.runner import run_command


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

    df_result = run_command(
        [
            "df",
            "--block-size=1M",
            "--output=source,size,used,avail,pcent,target",
            "-x",
            "tmpfs",
            "-x",
            "devtmpfs",
            "-x",
            "squashfs",
        ]
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

    home_total_result = run_command(["du", "-sm", str(Path.home())], timeout=90)
    home_total_mb = 0
    if home_total_result.stdout:
        try:
            home_total_mb = int(home_total_result.stdout.split("\t")[0])
        except (ValueError, IndexError):
            pass

    system_mb = max(0, used_mb - home_total_mb)

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

    home_paths = [str(Path.home() / suffix) for suffix, _ in home_dirs]
    du_result = run_command(["du", "-sm", *home_paths], timeout=60)

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

    dir_sizes.sort(key=lambda item: item[1], reverse=True)
    accounted_home_mb = sum(mb for _, mb in dir_sizes)
    other_home_mb = max(0, home_total_mb - accounted_home_mb)

    lines.append(
        f"DRIVE TOTAL: {_fmt_size(total_mb)}  "
        f"USED: {_fmt_size(used_mb)} ({_pct(used_mb, total_mb)})  "
        f"FREE: {_fmt_size(free_mb)}"
    )
    lines.append(f"  {_bar(used_mb, total_mb, 50)}")
    lines.append("")

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

    flatpak_result = run_command(["flatpak", "list", "--columns=name,size"])
    if flatpak_result.returncode == 0 and flatpak_result.stdout.strip():
        lines.append("FLATPAK APPS (installed size)")
        for flatpak_line in flatpak_result.stdout.strip().splitlines():
            lines.append(f"  {flatpak_line}")
        lines.append("")

    podman_result = run_command(["podman", "system", "df"])
    if podman_result.returncode == 0 and podman_result.stdout.strip():
        lines.append("PODMAN STORAGE")
        for podman_line in podman_result.stdout.strip().splitlines():
            lines.append(f"  {podman_line}")
        lines.append("")

    journal_result = run_command(["journalctl", "--disk-usage"])
    if journal_result.returncode == 0:
        lines.append(f"JOURNAL LOGS: {journal_result.stdout.strip()}")
        lines.append("")

    brew_cache_mb = 0
    brew_result = run_command(["brew", "--cache"], env={"HOMEBREW_NO_AUTO_UPDATE": "1"})
    if brew_result.returncode == 0 and brew_result.stdout.strip():
        brew_cache_path = brew_result.stdout.strip()
        brew_du = run_command(["du", "-sm", brew_cache_path], timeout=30)
        if brew_du.returncode == 0:
            try:
                brew_cache_mb = int(brew_du.stdout.split("\t")[0])
            except (ValueError, IndexError):
                pass
    if brew_cache_mb > 0:
        lines.append(f"BREW CACHE: {_fmt_size(brew_cache_mb)}")
        lines.append("")

    return "\n".join(lines)


def system_doctor() -> str:
    """Run security and health checks with PASS, WARN, and FAIL assessments."""
    lines: list[str] = []

    lines.append("SECURITY")

    fw_result = run_command(["firewall-cmd", "--get-default-zone"])
    if fw_result.returncode == 0:
        zone = fw_result.stdout.strip()
        if zone == "public":
            lines.append(f"  PASS  Firewall default zone: {zone}")
        else:
            lines.append(f"  FAIL  Firewall default zone: {zone} (expected: public)")
    else:
        lines.append("  FAIL  Firewall: could not query")

    svc_result = run_command(["firewall-cmd", "--list-services"])
    if svc_result.returncode == 0:
        services = set(svc_result.stdout.strip().split())
        expected = {"dhcpv6-client"}
        unexpected = services - expected
        if not unexpected:
            lines.append(f"  PASS  Firewall services: {', '.join(sorted(services)) or 'none'}")
        else:
            lines.append(f"  WARN  Firewall unexpected services: {', '.join(sorted(unexpected))}")

    dns_parts: list[str] = []
    dns_ok = True
    resolve_result = run_command(["systemctl", "is-active", "systemd-resolved"])
    if resolve_result.stdout.strip() == "active":
        resolvectl = run_command(["resolvectl", "status"])
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
                    ["cat", "/etc/systemd/resolved.conf.d/20-encrypted-dns.conf"]
                )
                if cfg_result.returncode == 0 and "DNSOverTLS=yes" in cfg_result.stdout:
                    dns_parts.append("DoTLS configured")
                else:
                    dns_parts.append("DoTLS not configured")
                    dns_ok = False

        llmnr_result = run_command(
            ["cat", "/etc/systemd/resolved.conf.d/10-network-hardening.conf"]
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

    sysctl_checks = {
        "kernel.kptr_restrict": "1",
        "net.ipv4.conf.all.rp_filter": "1",
        "net.ipv6.conf.all.accept_redirects": "0",
    }
    sysctl_failures: list[str] = []
    for key, expected_val in sysctl_checks.items():
        proc_path = f"/proc/sys/{key.replace('.', '/')}"
        sysctl_result = run_command(["cat", proc_path])
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
    lines.append("HEALTH")

    failed_result = run_command(["systemctl", "--failed", "--no-legend"])
    if failed_result.returncode == 0:
        failed_lines = [
            line for line in failed_result.stdout.strip().splitlines() if line.strip()
        ]
        if not failed_lines:
            lines.append("  PASS  No failed systemd units")
        else:
            units = [
                part
                for line in failed_lines
                for part in line.split()
                if part.endswith(".service")
                or part.endswith(".socket")
                or part.endswith(".timer")
            ]
            lines.append(f"  WARN  Failed units: {', '.join(units)}")
    else:
        lines.append("  PASS  No failed systemd units")

    df_result = run_command(
        [
            "df",
            "--block-size=1M",
            "--output=size,used,avail,pcent,target",
            "-x",
            "tmpfs",
            "-x",
            "devtmpfs",
            "-x",
            "squashfs",
        ]
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

    podman_result = run_command(["podman", "system", "df"])
    if podman_result.returncode == 0:
        for podman_line in podman_result.stdout.splitlines():
            if "images" in podman_line.lower():
                parts = podman_line.split()
                for index, part in enumerate(parts):
                    if "reclaimable" in part.lower() or ("(" in part and "%" in part):
                        reclaim_size = parts[index - 1] if index > 0 else "0B"
                        if reclaim_size != "0B":
                            lines.append(
                                f"  WARN  Podman: {reclaim_size} reclaimable images"
                            )
                        else:
                            lines.append("  PASS  Podman: no reclaimable images")
                        break
                break

    snap_timer = run_command(["systemctl", "is-active", "snapper-timeline.timer"])
    if snap_timer.stdout.strip() == "active":
        snap_list = run_command(["snapper", "-c", "home", "list", "--columns", "number"])
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

    journal_result = run_command(["journalctl", "--disk-usage"])
    if journal_result.returncode == 0:
        journal_text = journal_result.stdout.strip()
        if "G" in journal_text.split("up")[-1] if "up" in journal_text else "":
            lines.append(f"  WARN  {journal_text}")
        else:
            lines.append(f"  PASS  {journal_text}")

    for svc_name, label in [("avahi-daemon", "Avahi"), ("cups.socket", "CUPS")]:
        svc_check = run_command(["systemctl", "is-enabled", svc_name])
        state = svc_check.stdout.strip()
        if state == "disabled":
            lines.append(f"  INFO  {label}: disabled")
        elif state == "enabled":
            lines.append(f"  INFO  {label}: enabled")

    return "\n".join(lines)
