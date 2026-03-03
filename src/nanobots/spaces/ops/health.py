#!/usr/bin/env python3
"""
health.py - System health check nanobot

Checks CPU load, memory, disk usage, running services, and temperatures.
Produces a clean markdown report. Works on any Linux system using only
stdlib and /proc + /sys filesystem reads.

Usage:
    nanobot ops/health [service1,service2,...]

Environment:
    NANOBOT_OUTPUT   - Path to write the markdown report
    NANOBOT_RUN_ID   - Unique run identifier
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

def get_hostname() -> str:
    """Read system hostname."""
    try:
        return Path("/etc/hostname").read_text().strip()
    except Exception:
        return os.uname().nodename


def get_uptime() -> str:
    """Human-readable uptime from /proc/uptime."""
    try:
        raw = Path("/proc/uptime").read_text().strip()
        total_seconds = int(float(raw.split()[0]))
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)
    except Exception:
        return "unknown"


def get_cpu_cores() -> int:
    """Count online CPU cores from /proc/cpuinfo."""
    try:
        text = Path("/proc/cpuinfo").read_text()
        return text.count("processor\t:")
    except Exception:
        return os.cpu_count() or 1


def get_load_average() -> tuple[float, float, float]:
    """Load averages from /proc/loadavg."""
    try:
        parts = Path("/proc/loadavg").read_text().strip().split()
        return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception:
        return 0.0, 0.0, 0.0


def get_memory() -> dict:
    """Parse /proc/meminfo into a dict of key values in kB."""
    info: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" not in line:
                continue
            key, rest = line.split(":", 1)
            value = rest.strip().split()[0]
            info[key.strip()] = int(value)
    except Exception:
        pass
    return info


def get_disk_usage() -> list[dict]:
    """Disk usage for mounted filesystems via df."""
    disks = []
    try:
        result = subprocess.run(
            ["df", "-h", "--output=target,size,used,avail,pcent,fstype"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue
            mount = parts[0]
            # Skip virtual filesystems
            fstype = parts[5]
            if fstype in (
                "tmpfs", "devtmpfs", "squashfs", "overlay",
                "efivarfs", "proc", "sysfs", "devpts", "cgroup2",
                "securityfs", "pstore", "bpf", "tracefs",
                "debugfs", "hugetlbfs", "mqueue", "configfs",
                "fusectl", "ramfs", "rpc_pipefs", "nfsd",
            ):
                continue
            disks.append({
                "mount": mount,
                "size": parts[1],
                "used": parts[2],
                "avail": parts[3],
                "pct": parts[4],
                "fstype": fstype,
            })
    except Exception:
        pass
    return disks


def get_service_status(services: list[str]) -> list[dict]:
    """Check systemd service status via systemctl."""
    results = []
    if not services:
        return results

    for svc in services:
        svc = svc.strip()
        if not svc:
            continue
        entry = {"name": svc, "active": "unknown", "status": "unknown"}
        try:
            result = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True, timeout=5,
            )
            entry["active"] = result.stdout.strip()
            entry["status"] = "running" if entry["active"] == "active" else entry["active"]
        except FileNotFoundError:
            entry["status"] = "systemctl not available"
        except Exception as exc:
            entry["status"] = str(exc)
        results.append(entry)
    return results


def get_temperatures() -> list[dict]:
    """Read temperatures from /sys/class/thermal/ and /sys/class/hwmon/."""
    temps = []

    # Thermal zones
    thermal_base = Path("/sys/class/thermal")
    if thermal_base.is_dir():
        for zone in sorted(thermal_base.iterdir()):
            if not zone.name.startswith("thermal_zone"):
                continue
            try:
                temp_raw = (zone / "temp").read_text().strip()
                temp_c = int(temp_raw) / 1000.0
                try:
                    label = (zone / "type").read_text().strip()
                except Exception:
                    label = zone.name
                temps.append({"label": label, "temp_c": temp_c})
            except Exception:
                continue

    # hwmon sensors
    hwmon_base = Path("/sys/class/hwmon")
    if hwmon_base.is_dir():
        for hwmon in sorted(hwmon_base.iterdir()):
            try:
                hw_name = (hwmon / "name").read_text().strip()
            except Exception:
                hw_name = hwmon.name
            for f in sorted(hwmon.iterdir()):
                if f.name.startswith("temp") and f.name.endswith("_input"):
                    try:
                        temp_c = int(f.read_text().strip()) / 1000.0
                        idx = f.name.replace("temp", "").replace("_input", "")
                        label_file = hwmon / f"temp{idx}_label"
                        if label_file.exists():
                            label = label_file.read_text().strip()
                        else:
                            label = f"{hw_name}/temp{idx}"
                        # Deduplicate with thermal zones
                        if not any(t["label"] == label and abs(t["temp_c"] - temp_c) < 0.5 for t in temps):
                            temps.append({"label": label, "temp_c": temp_c})
                    except Exception:
                        continue

    return temps


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def load_status(load1: float, cores: int) -> str:
    """Evaluate load average relative to core count."""
    ratio = load1 / cores if cores else load1
    if ratio < 0.7:
        return "OK"
    elif ratio < 1.0:
        return "WARN"
    else:
        return "CRITICAL"


def memory_status(used_pct: float) -> str:
    if used_pct < 70:
        return "OK"
    elif used_pct < 90:
        return "WARN"
    else:
        return "CRITICAL"


def disk_status(pct_str: str) -> str:
    try:
        pct = int(pct_str.replace("%", ""))
    except ValueError:
        return "UNKNOWN"
    if pct < 80:
        return "OK"
    elif pct < 95:
        return "WARN"
    else:
        return "CRITICAL"


def temp_status(temp_c: float) -> str:
    if temp_c < 60:
        return "OK"
    elif temp_c < 80:
        return "WARN"
    else:
        return "CRITICAL"


def status_icon(status: str) -> str:
    return {"OK": "+", "WARN": "!", "CRITICAL": "x"}.get(status, "?")


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(services_list: list[str]) -> str:
    """Build the full markdown health report."""
    run_id = os.environ.get("NANOBOT_RUN_ID", "unknown")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    hostname = get_hostname()

    lines: list[str] = []
    overall_status = "OK"

    def escalate(status: str):
        nonlocal overall_status
        if status == "CRITICAL":
            overall_status = "CRITICAL"
        elif status == "WARN" and overall_status != "CRITICAL":
            overall_status = "WARN"

    lines.append(f"# System Health Report")
    lines.append(f"")
    lines.append(f"**Host:** {hostname}  ")
    lines.append(f"**Time:** {now}  ")
    lines.append(f"**Uptime:** {get_uptime()}")
    lines.append(f"")

    # --- CPU / Load ---
    cores = get_cpu_cores()
    load1, load5, load15 = get_load_average()
    cpu_stat = load_status(load1, cores)
    escalate(cpu_stat)

    lines.append(f"## CPU & Load")
    lines.append(f"")
    lines.append(f"| Metric | Value | Status |")
    lines.append(f"|--------|-------|--------|")
    lines.append(f"| Cores | {cores} | - |")
    lines.append(f"| Load 1m | {load1:.2f} | [{status_icon(cpu_stat)}] {cpu_stat} |")
    lines.append(f"| Load 5m | {load5:.2f} | - |")
    lines.append(f"| Load 15m | {load15:.2f} | - |")
    lines.append(f"| Load/Core | {load1/cores:.2f} | - |")
    lines.append(f"")

    # --- Memory ---
    mem = get_memory()
    total_kb = mem.get("MemTotal", 0)
    avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
    used_kb = total_kb - avail_kb
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    swap_used = swap_total - swap_free

    used_pct = (used_kb / total_kb * 100) if total_kb else 0
    mem_stat = memory_status(used_pct)
    escalate(mem_stat)

    def fmt_mb(kb: int) -> str:
        mb = kb / 1024
        if mb > 1024:
            return f"{mb/1024:.1f} GB"
        return f"{mb:.0f} MB"

    lines.append(f"## Memory")
    lines.append(f"")
    lines.append(f"| Metric | Value | Status |")
    lines.append(f"|--------|-------|--------|")
    lines.append(f"| Total | {fmt_mb(total_kb)} | - |")
    lines.append(f"| Used | {fmt_mb(used_kb)} ({used_pct:.1f}%) | [{status_icon(mem_stat)}] {mem_stat} |")
    lines.append(f"| Available | {fmt_mb(avail_kb)} | - |")
    if swap_total:
        swap_pct = (swap_used / swap_total * 100) if swap_total else 0
        lines.append(f"| Swap | {fmt_mb(swap_used)}/{fmt_mb(swap_total)} ({swap_pct:.1f}%) | - |")
    else:
        lines.append(f"| Swap | none | - |")
    lines.append(f"")

    # --- Disk ---
    disks = get_disk_usage()
    lines.append(f"## Disk Usage")
    lines.append(f"")
    if disks:
        lines.append(f"| Mount | Size | Used | Avail | Use% | Status |")
        lines.append(f"|-------|------|------|-------|------|--------|")
        for d in disks:
            ds = disk_status(d["pct"])
            escalate(ds)
            lines.append(
                f"| {d['mount']} | {d['size']} | {d['used']} | {d['avail']} "
                f"| {d['pct']} | [{status_icon(ds)}] {ds} |"
            )
    else:
        lines.append("No mounted filesystems detected.")
    lines.append(f"")

    # --- Services ---
    svc_results = get_service_status(services_list)
    if svc_results:
        lines.append(f"## Services")
        lines.append(f"")
        lines.append(f"| Service | Status |")
        lines.append(f"|---------|--------|")
        for svc in svc_results:
            if svc["status"] == "running":
                icon = "[+] running"
            elif svc["status"] in ("inactive", "dead"):
                icon = "[x] stopped"
                escalate("WARN")
            elif svc["status"] == "failed":
                icon = "[x] failed"
                escalate("CRITICAL")
            else:
                icon = f"[?] {svc['status']}"
            lines.append(f"| {svc['name']} | {icon} |")
        lines.append(f"")

    # --- Temperatures ---
    temps = get_temperatures()
    if temps:
        lines.append(f"## Temperatures")
        lines.append(f"")
        lines.append(f"| Sensor | Temp | Status |")
        lines.append(f"|--------|------|--------|")
        for t in temps:
            ts = temp_status(t["temp_c"])
            escalate(ts)
            lines.append(
                f"| {t['label']} | {t['temp_c']:.1f} C | [{status_icon(ts)}] {ts} |"
            )
        lines.append(f"")

    # --- Overall ---
    lines.append(f"## Overall: {overall_status}")
    lines.append(f"")

    # --- Footer ---
    lines.append(f"---")
    lines.append(f"*nanobot run `{run_id}` | ops/health | {now}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Parse services from argv
    services: list[str] = []
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
        services = [s.strip() for s in raw.split(",") if s.strip()]

    report = build_report(services)

    # Write to output path
    output_path = os.environ.get("NANOBOT_OUTPUT")
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report)
    else:
        print(report)


if __name__ == "__main__":
    main()
