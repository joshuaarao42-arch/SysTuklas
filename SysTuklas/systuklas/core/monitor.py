"""System monitoring layer: samples hardware/OS metrics on background threads.

Nothing in this module touches the GUI. The UI only *reads* the latest
results (``monitor.latest``, ``monitor.get_history()``, ``procs.get_rows()``),
so slow system calls can never freeze the interface.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Callable, Optional

import psutil

from .models import Snapshot, aggregate_apps

log = logging.getLogger("systuklas.monitor")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def system_drive() -> str:
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


def _read_temperature() -> Optional[float]:
    fn = getattr(psutil, "sensors_temperatures", None)
    if fn is None:
        return None
    try:
        data = fn()
    except Exception:
        return None
    best = None
    for entries in (data or {}).values():
        for e in entries:
            if e.current is not None and 0 < e.current < 150:
                best = e.current if best is None else max(best, e.current)
    return best


def _read_battery():
    fn = getattr(psutil, "sensors_battery", None)
    try:
        b = fn() if fn else None
    except Exception:
        b = None
    if b is None:
        return None, None
    return b.percent, b.power_plugged


READONLY_FS = {"squashfs", "iso9660", "udf", "cdfs", "erofs"}


def read_disks() -> list:
    """All mounted drives with capacity information (skips unreadable ones)."""
    disks = []
    try:
        parts = psutil.disk_partitions(all=False)
    except Exception:
        return disks
    for p in parts:
        if "cdrom" in p.opts.lower() or not p.fstype:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append({
            "device": p.device, "mountpoint": p.mountpoint, "fstype": p.fstype,
            "total": u.total, "used": u.used, "free": u.free, "percent": u.percent,
            "readonly": "ro" in p.opts.lower().split(",") or p.fstype.lower() in READONLY_FS,
        })
    return disks


def read_interfaces() -> list:
    rows = []
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        io = psutil.net_io_counters(pernic=True)
    except Exception:
        return rows
    for name, st in stats.items():
        ipv4 = ""
        for a in addrs.get(name, []):
            if a.family == socket.AF_INET:
                ipv4 = a.address
                break
        c = io.get(name)
        rows.append({
            "name": name, "up": st.isup, "speed": st.speed, "ipv4": ipv4,
            "sent": c.bytes_sent if c else 0, "recv": c.bytes_recv if c else 0,
        })
    rows.sort(key=lambda r: (not r["up"], r["name"].lower()))
    return rows


def count_connections() -> Optional[int]:
    try:
        conns = psutil.net_connections(kind="inet")
    except Exception:
        return None
    return sum(1 for c in conns if c.status == psutil.CONN_ESTABLISHED)


# --------------------------------------------------------------------------- #
# live system monitor
# --------------------------------------------------------------------------- #
class SystemMonitor:
    """Samples CPU / RAM / disk / network once per ``interval`` seconds."""

    def __init__(self, interval: float = 1.0, history_len: int = 300):
        self.interval = interval
        self._history = deque(maxlen=history_len)
        self._latest: Optional[Snapshot] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._listeners: list = []
        self.logical_cores = psutil.cpu_count(logical=True) or 1
        self.physical_cores = psutil.cpu_count(logical=False) or self.logical_cores
        self.disks: list = []
        self.interfaces: list = []
        self.connections: Optional[int] = None
        self.disk_io_supported = True
        self.net_base_sent = 0
        self.net_base_recv = 0
        self.peak_down = 0.0
        self.peak_up = 0.0
        self._slow_at = {"disks": 0.0, "ifaces": 0.0, "conns": 0.0}

    # ----- public API -----
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="SysTuklas-Monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def add_listener(self, cb: Callable[[Snapshot], None]) -> None:
        self._listeners.append(cb)

    @property
    def latest(self) -> Optional[Snapshot]:
        with self._lock:
            return self._latest

    def get_history(self, last: Optional[int] = None) -> list:
        with self._lock:
            data = list(self._history)
        return data[-last:] if last else data

    def get_disks(self) -> list:
        return list(self.disks)

    def get_interfaces(self) -> list:
        return list(self.interfaces)

    def session_totals(self):
        s = self.latest
        if not s:
            return 0, 0
        return max(0, s.net_sent_total - self.net_base_sent), max(0, s.net_recv_total - self.net_base_recv)

    # ----- internals -----
    def _counters(self) -> dict:
        net = disk = None
        try:
            net = psutil.net_io_counters()
        except Exception:
            pass
        try:
            disk = psutil.disk_io_counters()
        except Exception:
            pass
        return {"t": time.time(), "net": net, "disk": disk}

    def _refresh_slow(self, force: bool = False) -> None:
        now = time.time()
        if force or now - self._slow_at["disks"] >= 10:
            self.disks = read_disks()
            self._slow_at["disks"] = now
        if force or now - self._slow_at["ifaces"] >= 5:
            self.interfaces = read_interfaces()
            self._slow_at["ifaces"] = now
        if force or now - self._slow_at["conns"] >= 30:
            self.connections = count_connections()
            self._slow_at["conns"] = now

    def _loop(self) -> None:
        psutil.cpu_percent(None, percpu=True)  # prime the counters
        prev = self._counters()
        if prev["net"]:
            self.net_base_sent, self.net_base_recv = prev["net"].bytes_sent, prev["net"].bytes_recv
        try:
            self._refresh_slow(force=True)
        except Exception:
            log.exception("initial slow refresh failed")
        while not self._stop.wait(self.interval):
            try:
                cur = self._counters()
                snap = self._build(cur, prev)
                prev = cur
                with self._lock:
                    self._history.append(snap)
                    self._latest = snap
                self.peak_down = max(self.peak_down, snap.net_down_bps)
                self.peak_up = max(self.peak_up, snap.net_up_bps)
                self._refresh_slow()
                for cb in list(self._listeners):
                    try:
                        cb(snap)
                    except Exception:
                        log.exception("listener failed")
            except Exception:
                log.exception("sampling failed")

    def _build(self, cur: dict, prev: dict) -> Snapshot:
        dt = max(cur["t"] - prev["t"], 1e-3)
        per_core = psutil.cpu_percent(None, percpu=True) or [0.0]
        cpu = sum(per_core) / len(per_core)

        f_cur = f_max = None
        try:
            f = psutil.cpu_freq()
            if f:
                f_cur, f_max = f.current or None, f.max or None
        except Exception:
            pass

        vm = psutil.virtual_memory()
        ram_used = max(0, vm.total - vm.available)
        ram_pct = ram_used / vm.total * 100 if vm.total else 0.0
        try:
            sw = psutil.swap_memory()
            swap_total, swap_used, swap_pct = sw.total, sw.used, sw.percent
        except Exception:
            swap_total = swap_used = 0
            swap_pct = 0.0

        try:
            du = psutil.disk_usage(system_drive())
            d_pct, d_free, d_total = du.percent, du.free, du.total
        except Exception:
            d_pct, d_free, d_total = 0.0, 0, 0

        d_read = d_write = 0.0
        if cur["disk"] is not None and prev["disk"] is not None:
            d_read = max(0.0, (cur["disk"].read_bytes - prev["disk"].read_bytes) / dt)
            d_write = max(0.0, (cur["disk"].write_bytes - prev["disk"].write_bytes) / dt)
        else:
            self.disk_io_supported = False

        n_up = n_down = 0.0
        sent = recv = 0
        if cur["net"] is not None:
            sent, recv = cur["net"].bytes_sent, cur["net"].bytes_recv
            if prev["net"] is not None:
                n_up = max(0.0, (sent - prev["net"].bytes_sent) / dt)
                n_down = max(0.0, (recv - prev["net"].bytes_recv) / dt)

        batt_pct, batt_plug = _read_battery()
        return Snapshot(
            ts=cur["t"], cpu=cpu, per_core=per_core, freq_current=f_cur, freq_max=f_max,
            ram_percent=ram_pct, ram_total=vm.total, ram_used=ram_used, ram_available=vm.available,
            swap_percent=swap_pct, swap_total=swap_total, swap_used=swap_used,
            disk_percent=d_pct, disk_free=d_free, disk_total=d_total,
            disk_read_bps=d_read, disk_write_bps=d_write,
            net_up_bps=n_up, net_down_bps=n_down, net_sent_total=sent, net_recv_total=recv,
            temperature=_read_temperature(), battery_percent=batt_pct, battery_plugged=batt_plug,
        )


# --------------------------------------------------------------------------- #
# process sampler
# --------------------------------------------------------------------------- #
class ProcessSampler:
    """Collects the process table on a background thread (default every 3 s)."""

    def __init__(self, interval: float = 4.0):
        self.interval = interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._rows: list = []
        self._users: dict = {}
        self.version = 0
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="SysTuklas-Procs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def request_refresh(self) -> None:
        self._wake.set()

    def get_rows(self) -> list:
        with self._lock:
            return list(self._rows)

    def get_apps(self) -> list:
        return aggregate_apps(self.get_rows())

    def _loop(self) -> None:
        first = True
        last = 0.0
        while not self._stop.is_set():
            gap = 1.0 - (time.time() - last)
            if gap > 0:  # psutil needs ~1 s between reads for meaningful CPU %
                time.sleep(gap)
            try:
                rows = self._collect()
                with self._lock:
                    self._rows = rows
                    self.version += 1
            except Exception:
                log.exception("process collection failed")
            last = time.time()
            if first:
                first = False
                self._stop.wait(1.0)
            else:
                self._wake.wait(self.interval)
            self._wake.clear()

    def _user_of(self, p, budget: list) -> str:
        """Owner lookup is slow on Windows, so cache it and limit new lookups per cycle."""
        pid = p.pid
        if pid in self._users:
            return self._users[pid]
        if budget[0] <= 0:
            return ""
        budget[0] -= 1
        try:
            user = p.username() or ""
        except Exception:
            user = ""
        if "\\" in user:
            user = user.split("\\")[-1]
        self._users[pid] = user
        return user

    def _collect(self) -> list:
        ncpu = psutil.cpu_count() or 1
        attrs = ["pid", "name", "cpu_percent", "memory_info", "num_threads", "status"]
        rows = []
        budget = [25]
        alive = set()
        for p in psutil.process_iter(attrs):
            info = p.info
            pid = info.get("pid")
            name = info.get("name") or ""
            if pid == 0 or name == "System Idle Process":
                continue
            mi = info.get("memory_info")
            alive.add(pid)
            user = self._user_of(p, budget)
            rows.append({
                "pid": pid, "name": name or f"PID {pid}",
                "cpu": (info.get("cpu_percent") or 0.0) / ncpu,
                "rss": mi.rss if mi else 0,
                "threads": info.get("num_threads") or 0,
                "status": info.get("status") or "",
                "user": user,
            })
        for pid in set(self._users) - alive:
            self._users.pop(pid, None)
        return rows


CRITICAL_NAMES = {
    "system", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe",
    "registry", "memory compression", "init", "systemd", "launchd", "kernel_task",
}


def protection_level(pid: int, name: str) -> Optional[str]:
    """'blocked' = never allow, 'critical' = allow with strong warning, None = normal."""
    if pid == os.getpid() or pid in (0, 4) or (name or "").lower() == "system":
        return "blocked"
    if (name or "").lower() in CRITICAL_NAMES:
        return "critical"
    return None


def terminate_process(pid: int, force: bool = False, timeout: float = 3.0) -> bool:
    """Terminate (or kill) a process. Returns True if it is gone afterwards.
    Raises psutil.NoSuchProcess / psutil.AccessDenied for the caller to report."""
    p = psutil.Process(pid)
    if force:
        p.kill()
    else:
        p.terminate()
    try:
        p.wait(timeout)
        return True
    except psutil.TimeoutExpired:
        return False


def get_process_details(pid: int) -> list:
    """Returns [(label, value), ...] describing one process. Raises NoSuchProcess."""
    from .formatting import fmt_bytes, fmt_duration, fmt_time

    p = psutil.Process(pid)

    def s(fn, default="Not available"):
        try:
            v = fn()
            return default if v in (None, "") else v
        except (psutil.AccessDenied, psutil.ZombieProcess):
            return "Access denied"
        except psutil.NoSuchProcess:
            raise
        except Exception:
            return default

    with p.oneshot():
        name = s(p.name)
        created = s(p.create_time, None)
        mem = s(p.memory_info, None)
        cpu_t = s(p.cpu_times, None)
        parent = s(p.parent, None)
        cmd = s(p.cmdline, None)
        handles_fn = getattr(p, "num_handles", None) or getattr(p, "num_fds", None)
        io = s(p.io_counters, None) if hasattr(p, "io_counters") else None
        details = [
            ("Name", name),
            ("PID", pid),
            ("Status", s(p.status)),
            ("User", s(p.username)),
            ("Executable", s(p.exe)),
            ("Command line", " ".join(cmd) if isinstance(cmd, list) and cmd else (cmd or "Not available")),
            ("Working directory", s(p.cwd)),
            ("Started", fmt_time(created) if isinstance(created, float) else created or "Not available"),
            ("Running for", fmt_duration(time.time() - created) if isinstance(created, float) else "Not available"),
            ("Parent process", f"{parent.name()} (PID {parent.pid})" if parent not in (None, "Access denied") else "None / not available"),
            ("Child processes", s(lambda: len(p.children()), 0)),
            ("Threads", s(p.num_threads)),
            ("CPU usage (now)", f"{s(lambda: p.cpu_percent(None), 0.0) / (psutil.cpu_count() or 1):.1f} %"),
            ("CPU time (user / system)", f"{cpu_t.user:.1f}s / {cpu_t.system:.1f}s" if hasattr(cpu_t, "user") else "Not available"),
            ("Memory (working set)", fmt_bytes(mem.rss) if hasattr(mem, "rss") else "Not available"),
            ("Memory (virtual)", fmt_bytes(mem.vms) if hasattr(mem, "vms") else "Not available"),
            ("Handles / file descriptors", s(handles_fn) if handles_fn else "Not available"),
            ("Priority", s(p.nice)),
        ]
        if hasattr(io, "read_bytes"):
            details.append(("Disk I/O (read / written)", f"{fmt_bytes(io.read_bytes)} / {fmt_bytes(io.write_bytes)}"))
    return details


# --------------------------------------------------------------------------- #
# static hardware information
# --------------------------------------------------------------------------- #
def _cpu_name() -> str:
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
    return platform.processor() or platform.machine() or "Unknown processor"


def _powershell_json(cmd: str, timeout: int = 15) -> Optional[list]:
    if os.name != "nt":
        return None
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout, creationflags=flags,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        data = json.loads(out.stdout)
        return data if isinstance(data, list) else [data]
    except Exception:
        return None


class HardwareInfo:
    """Static hardware facts. GPU and physical-disk health are probed in the
    background because PowerShell can take a few seconds."""

    def __init__(self):
        boot = psutil.boot_time()
        vm = psutil.virtual_memory()
        self.data = {
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
            "os_version": platform.version(),
            "machine": platform.machine(),
            "cpu_name": _cpu_name(),
            "physical_cores": psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
            "logical_cores": psutil.cpu_count() or 1,
            "ram_total": vm.total,
            "boot_time": boot,
        }
        self.gpu = "Detecting…"
        self.physical_disks: Optional[list] = None   # None = still probing
        self.disks_probed = False

    def uptime(self) -> float:
        return time.time() - self.data["boot_time"]

    def probe_async(self) -> None:
        threading.Thread(target=self._probe, name="SysTuklas-HW", daemon=True).start()

    def _probe(self) -> None:
        try:
            rows = _powershell_json(
                "Get-CimInstance Win32_VideoController | Select-Object Name | ConvertTo-Json -Compress")
            names = [r.get("Name") for r in (rows or []) if r.get("Name")]
            self.gpu = ", ".join(names) if names else "Not detected"
        except Exception:
            self.gpu = "Not detected"
        disks = []
        try:
            rows = _powershell_json(
                'Get-PhysicalDisk | Select-Object FriendlyName,'
                '@{n="Type";e={"$($_.MediaType)"}},@{n="Health";e={"$($_.HealthStatus)"}},'
                '@{n="Status";e={"$($_.OperationalStatus)"}},Size | ConvertTo-Json -Compress')
            for r in rows or []:
                disks.append({"name": r.get("FriendlyName") or "Disk", "type": r.get("Type") or "Unknown",
                              "health": r.get("Health") or "Unknown", "status": r.get("Status") or "Unknown",
                              "size": r.get("Size") or 0})
            if not disks:
                rows = _powershell_json(
                    "Get-CimInstance Win32_DiskDrive | Select-Object Model,Status,Size,InterfaceType | ConvertTo-Json -Compress")
                for r in rows or []:
                    ok = (r.get("Status") or "").upper() == "OK"
                    disks.append({"name": r.get("Model") or "Disk", "type": r.get("InterfaceType") or "Unknown",
                                  "health": "Healthy" if ok else (r.get("Status") or "Unknown"),
                                  "status": r.get("Status") or "Unknown", "size": r.get("Size") or 0})
        except Exception:
            log.exception("disk health probe failed")
        self.physical_disks = disks
        self.disks_probed = True
