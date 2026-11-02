"""Diagnostic engine: turns raw measurements into plain-language findings.

Design rules
------------
* Judge *sustained* behaviour (averages / share of time over a window), never a
  single reading. A momentary spike is normal and is reported as such.
* Only report a hardware problem when the operating system itself reports one
  (e.g. a drive health status). High utilisation is never called a failure.
* Every finding has a measured detail and, where useful, a concrete next step.
"""
from __future__ import annotations

import time
from typing import Optional

from .formatting import fmt_bytes, fmt_duration, fmt_rate
from .models import DiagnosticReport, Finding, Snapshot, aggregate_apps

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
SEVERITY_LABELS = {"critical": "Critical", "warning": "Warning", "info": "Notice", "ok": "Healthy"}

DISCLAIMER = (
    "SysTuklas analyses utilisation measurements. Brief spikes in CPU, memory or disk activity are a normal "
    "part of computer use and are not signs of hardware failure. A hardware problem is reported only when "
    "the operating system itself reports one."
)


def _avg(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _share_above(xs, thr: float) -> float:
    xs = list(xs)
    return sum(1 for x in xs if x > thr) / len(xs) if xs else 0.0


def _names(items, key, fmt, n=3) -> str:
    return ", ".join(f"{i['name']} ({fmt(i[key])})" for i in items[:n])


class DiagnosticEngine:
    # thresholds -------------------------------------------------------------
    CPU_SUSTAINED = 85.0
    CPU_CRITICAL = 95.0
    RAM_ELEVATED = 75.0
    RAM_HIGH = 85.0
    RAM_CRITICAL = 92.0
    DISK_FREE_WARN_PCT = 12.0
    DISK_FREE_CRIT_PCT = 5.0
    MIN_SAMPLES = 20

    def analyze(self, samples: list, processes: list, disks: list, system: dict,
                history_stats: Optional[dict] = None, physical_disks: Optional[list] = None) -> DiagnosticReport:
        now = time.time()
        findings: list = []
        notes: list = []
        samples = list(samples or [])
        apps = aggregate_apps(processes or [])
        n = len(samples)
        window = (samples[-1].ts - samples[0].ts) if n > 1 else 0.0
        limited = n < self.MIN_SAMPLES

        if n == 0:
            return DiagnosticReport(
                generated_at=now, health_score=100, health_label="Not enough data",
                summary="No measurements have been collected yet. Wait a few seconds and run the scan again.",
                findings=[Finding("info", "Data", "Not enough data",
                                  "SysTuklas has not collected any measurements yet.",
                                  "Wait a few seconds, then run the scan again.")],
                system=system, notes=[DISCLAIMER], window_seconds=0.0)

        last = samples[-1]
        metrics = {
            "samples": n,
            "window": fmt_duration(window),
            "cpu_avg": round(_avg(s.cpu for s in samples), 1),
            "cpu_peak": round(max(s.cpu for s in samples), 1),
            "ram_avg": round(_avg(s.ram_percent for s in samples), 1),
            "ram_peak": round(max(s.ram_percent for s in samples), 1),
            "swap_avg": round(_avg(s.swap_percent for s in samples), 1),
            "ram_available": fmt_bytes(last.ram_available),
            "system_drive_used": round(last.disk_percent, 1),
            "disk_io_avg": fmt_rate(_avg(s.disk_read_bps + s.disk_write_bps for s in samples)),
            "net_down_avg": fmt_rate(_avg(s.net_down_bps for s in samples)),
            "net_up_avg": fmt_rate(_avg(s.net_up_bps for s in samples)),
            "processes": len(processes or []),
        }

        self._cpu(findings, samples, apps, window, limited)
        self._memory(findings, samples, apps, limited)
        self._storage(findings, samples, disks, physical_disks, notes)
        self._network(findings, samples)
        self._sensors(findings, samples, notes)
        self._uptime(findings, system)
        self._top_consumers(findings, apps)
        self._history(findings, samples, history_stats, notes)

        if limited:
            notes.append(f"Only {n} measurements ({fmt_duration(window)}) were available, so the results are "
                         "preliminary. Run the scan again after the computer has been used for a few minutes.")
        notes.append(DISCLAIMER)

        findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
        score = self._score(findings)
        label = ("Excellent" if score >= 90 else "Good" if score >= 75
                 else "Needs attention" if score >= 55 else "Poor")
        summary = self._summary(findings, limited)
        return DiagnosticReport(generated_at=now, health_score=score, health_label=label, summary=summary,
                                findings=findings, metrics=metrics, system=system, notes=notes,
                                window_seconds=window)

    # ------------------------------------------------------------------ checks
    def _cpu(self, out, samples, apps, window, limited):
        cpu = [s.cpu for s in samples]
        avg, peak = _avg(cpu), max(cpu)
        hot = _share_above(cpu, 90)
        culprits = sorted((a for a in apps if a["cpu"] >= 8), key=lambda a: a["cpu"], reverse=True)
        cul = _names(culprits, "cpu", lambda v: f"{v:.0f}%")
        span = fmt_duration(window) if window else "the measured period"

        if avg >= self.CPU_SUSTAINED or hot >= 0.6:
            sev = "critical" if avg >= self.CPU_CRITICAL and not limited else "warning"
            if cul:
                rec = (f"The busiest programs right now are {cul}. Close or restart them if you are not using them. "
                       "If it stays high with nothing heavy running, check for a running antivirus scan, Windows "
                       "Update or indexing, which usually finish by themselves.")
            else:
                rec = ("No single program stands out. Check whether Windows Update, an antivirus scan or file "
                       "indexing is running; they normally finish on their own. If the load never drops, run a "
                       "malware scan.")
            out.append(Finding(sev, "CPU", "CPU has been busy for a sustained period",
                               f"CPU usage averaged {avg:.0f}% over {span} and was above 90% for {hot * 100:.0f}% "
                               f"of that time (peak {peak:.0f}%).", rec))
        elif peak >= 90 and avg < 60:
            out.append(Finding("info", "CPU", "Short CPU spikes detected (normal)",
                               f"CPU briefly reached {peak:.0f}% but averaged only {avg:.0f}%. Short spikes happen "
                               "when programs open or pages load and are not a sign of a problem."))
        elif avg >= 60:
            out.append(Finding("info", "CPU", "CPU load is moderate-to-high",
                               f"CPU usage averaged {avg:.0f}% (peak {peak:.0f}%).",
                               f"Heavy programs: {cul}." if cul else ""))
        else:
            out.append(Finding("ok", "CPU", "CPU load is normal",
                               f"CPU usage averaged {avg:.0f}% with a peak of {peak:.0f}%."))

    def _memory(self, out, samples, apps, limited):
        last = samples[-1]
        ram = [s.ram_percent for s in samples]
        swap = [s.swap_percent for s in samples]
        ram_avg, swap_avg = _avg(ram), _avg(swap)
        total = last.ram_total
        top = sorted(apps, key=lambda a: a["rss"], reverse=True)
        top_txt = _names(top, "rss", fmt_bytes)
        low_ram_note = ("If this happens regularly, adding more RAM is the most effective upgrade."
                        if total <= 16 * 1024 ** 3 else "")
        flagged = False

        if ram_avg >= self.RAM_CRITICAL or last.ram_available < 512 * 1024 ** 2:
            sev = "warning" if limited else "critical"
            flagged = True
            out.append(Finding(sev, "Memory", "Memory is almost full",
                               f"{fmt_bytes(last.ram_used)} of {fmt_bytes(total)} is in use ({ram_avg:.0f}% average); "
                               f"only {fmt_bytes(last.ram_available)} is available. Largest users: {top_txt}.",
                               f"Save your work and close programs you are not using, especially {top[0]['name'] if top else 'large apps'}. "
                               "Browser tabs are a common cause. " + low_ram_note))
        elif ram_avg >= self.RAM_HIGH:
            flagged = True
            out.append(Finding("warning", "Memory", "Memory usage is high",
                               f"{ram_avg:.0f}% of {fmt_bytes(total)} is in use on average; {fmt_bytes(last.ram_available)} "
                               f"is still available. Largest users: {top_txt}.",
                               "Close programs or browser tabs you no longer need. " + low_ram_note))
        elif ram_avg >= self.RAM_ELEVATED:
            out.append(Finding("info", "Memory", "Memory usage is elevated",
                               f"{ram_avg:.0f}% of {fmt_bytes(total)} is in use. Largest users: {top_txt}.",
                               "Nothing is wrong yet, but opening more programs may slow the computer down."))
        else:
            out.append(Finding("ok", "Memory", "Memory usage is healthy",
                               f"{ram_avg:.0f}% of {fmt_bytes(total)} in use; {fmt_bytes(last.ram_available)} available."))

        if last.swap_total > 0:
            if swap_avg >= 60 and ram_avg >= 80:
                out.append(Finding("warning", "Memory", "Heavy use of virtual memory (page file)",
                                   f"The page file is {swap_avg:.0f}% full while RAM is {ram_avg:.0f}% used, so the "
                                   "system is using the much slower disk as extra memory.",
                                   "Close memory-hungry programs to relieve the pressure."))
            elif swap_avg >= 60 and ram_avg < 70:
                out.append(Finding("info", "Memory", "Page file is well used, but RAM is available",
                                   f"The page file is {swap_avg:.0f}% used while RAM is only {ram_avg:.0f}% used. "
                                   "This is usually left over from earlier heavy use and is not harmful.",
                                   "A restart clears it."))

        if not flagged and top and total:
            big = top[0]
            share = big["rss"] / total * 100
            if share >= 30:
                out.append(Finding("warning", "Memory", f"{big['name']} is using a large share of memory",
                                   f"{big['name']} uses {fmt_bytes(big['rss'])} ({share:.0f}% of all RAM) across "
                                   f"{big['count']} process(es).",
                                   f"If you are not actively using {big['name']}, closing or restarting it will free memory."))

    def _storage(self, out, samples, disks, physical, notes):
        problem = False
        # read-only media (disc images, squashfs) are always "full" by design - ignore them
        usable = [d for d in (disks or []) if d.get("total", 0) > 0 and not d.get("readonly")]
        for d in sorted(usable, key=lambda d: d["free"] / d["total"]):
            free_pct = d["free"] / d["total"] * 100
            name = d["mountpoint"]
            detail = (f"{name} has {fmt_bytes(d['free'])} free of {fmt_bytes(d['total'])} "
                      f"({free_pct:.0f}% free, {d['percent']:.0f}% used).")
            if free_pct < self.DISK_FREE_CRIT_PCT or d["free"] < 2 * 1024 ** 3:
                problem = True
                out.append(Finding("critical", "Storage", f"Drive {name} is almost full", detail,
                                   "Free up space now: empty the Recycle Bin, run Disk Cleanup, uninstall unused programs "
                                   "and move large files (videos, downloads) to another drive. Windows needs free space "
                                   "for updates and virtual memory."))
            elif free_pct < self.DISK_FREE_WARN_PCT or d["free"] < 10 * 1024 ** 3:
                problem = True
                out.append(Finding("warning", "Storage", f"Drive {name} is running low on space", detail,
                                   "Clean up large or unused files soon to keep the drive responsive."))
        if usable and not problem:
            low = min(usable, key=lambda d: d["free"] / d["total"])
            out.append(Finding("ok", "Storage", "Free disk space is healthy",
                               f"All {len(usable)} drive(s) have comfortable free space. Lowest: {low['mountpoint']} with "
                               f"{low['free'] / low['total'] * 100:.0f}% ({fmt_bytes(low['free'])}) free."))

        io = _avg(s.disk_read_bps + s.disk_write_bps for s in samples)
        if io >= 80 * 1024 ** 2:
            out.append(Finding("info", "Storage", "Sustained heavy disk activity",
                               f"The disk averaged {fmt_rate(io)} of reads and writes. This is normal during copying, "
                               "installing, updating or scanning.",
                               "If the computer feels slow when nothing like that is running, check the Processes page for the culprit."))

        if physical:
            bad = [p for p in physical if str(p.get("health", "")).strip().lower() not in ("healthy", "ok", "", "unknown")]
            for p in bad:
                sev = "critical" if str(p["health"]).lower() == "unhealthy" else "warning"
                out.append(Finding(sev, "Storage", f"Windows reports a health problem on '{p['name']}'",
                                   f"The operating system reports this drive's health as '{p['health']}' "
                                   f"(status: {p.get('status', 'unknown')}).",
                                   "Back up your important files now. Then check the drive with the manufacturer's tool "
                                   "or run 'chkdsk' and consider replacing the drive if the warning persists."))
            if not bad:
                out.append(Finding("ok", "Storage", "Drive health reported as healthy",
                                   f"Windows reports all {len(physical)} physical drive(s) as healthy."))
        else:
            notes.append("Drive health status was not available on this system, so only free space and activity were checked.")

    def _network(self, out, samples):
        down = _avg(s.net_down_bps for s in samples)
        up = _avg(s.net_up_bps for s in samples)
        if down >= 5 * 1024 ** 2 or up >= 2 * 1024 ** 2:
            out.append(Finding("info", "Network", "Heavy network traffic",
                               f"Average download {fmt_rate(down)}, upload {fmt_rate(up)}.",
                               "This is expected during downloads, game updates, cloud sync or streaming. "
                               "If you are not doing any of those, check which programs are running in the background."))

    def _sensors(self, out, samples, notes):
        temps = [s.temperature for s in samples if s.temperature is not None]
        if temps:
            recent = temps[-10:]
            if _avg(recent) >= 90:
                out.append(Finding("warning", "Temperature", "Processor temperature is high",
                                   f"The sensor reports an average of {_avg(recent):.0f}°C recently (peak {max(temps):.0f}°C). "
                                   "Sustained high temperatures can cause the processor to slow itself down.",
                                   "Make sure vents are not blocked, clean dust from fans, and use the laptop on a hard surface."))
            elif max(temps) >= 85:
                out.append(Finding("info", "Temperature", "Temperature briefly rose",
                                   f"Peak sensor temperature was {max(temps):.0f}°C, but it did not stay there. "
                                   "Short rises under load are normal."))
        else:
            notes.append("No temperature sensor is exposed by this system (common on Windows), so temperature was not assessed.")
        last = samples[-1]
        if last.battery_percent is not None and last.battery_plugged is False and last.battery_percent <= 15:
            out.append(Finding("warning", "Power", "Battery is low",
                               f"Battery is at {last.battery_percent:.0f}% and not charging.",
                               "Plug in the charger to avoid unexpected shutdown and reduced performance."))

    def _uptime(self, out, system):
        up = system.get("uptime_seconds") or 0
        if up >= 14 * 86400:
            out.append(Finding("info", "System", "The computer has not restarted for a while",
                               f"Uptime is {fmt_duration(up)}.",
                               "Restart to apply pending updates and release memory that long-running programs may be holding."))

    def _top_consumers(self, out, apps):
        if not apps:
            return
        by_cpu = sorted(apps, key=lambda a: a["cpu"], reverse=True)
        by_mem = sorted(apps, key=lambda a: a["rss"], reverse=True)
        out.append(Finding("info", "Processes", "Top resource consumers at the time of the scan",
                           f"CPU: {_names(by_cpu, 'cpu', lambda v: f'{v:.1f}%')}.  "
                           f"Memory: {_names(by_mem, 'rss', fmt_bytes)}."))

    def _history(self, out, samples, stats, notes):
        if not stats or stats.get("n", 0) < 30:
            notes.append("Not enough recorded history yet (needs a few minutes of data) for long-term analysis.")
            return
        span = fmt_duration(stats.get("span_seconds", 0))
        cpu_a, cpu_p = stats["cpu_avg"] or 0, stats["cpu_peak"] or 0
        ram_a, ram_p = stats["ram_avg"] or 0, stats["ram_peak"] or 0
        detail = (f"Over the recorded history ({span} of data): CPU averaged {cpu_a:.0f}% (peak {cpu_p:.0f}%), "
                  f"memory averaged {ram_a:.0f}% (peak {ram_p:.0f}%).")
        if ram_a >= 80:
            out.append(Finding("warning", "History", "Memory pressure is persistent, not a one-off", detail,
                               "Because this shows up in your history, reduce startup programs and heavy browser use, "
                               "or consider adding RAM."))
        elif cpu_a >= 70:
            out.append(Finding("warning", "History", "CPU load has been consistently high", detail,
                               "Review startup programs and background tasks; if your workload is legitimately heavy, "
                               "a faster processor would help."))
        else:
            out.append(Finding("ok", "History", "No long-term performance problems in your history", detail))
        now_cpu = _avg(s.cpu for s in samples)
        if cpu_a > 0 and now_cpu >= max(50.0, 2 * cpu_a):
            out.append(Finding("info", "History", "The computer is busier than usual right now",
                               f"CPU averaged {now_cpu:.0f}% in this scan versus a typical {cpu_a:.0f}%.",
                               "Something unusual may be running. Check the Processes page."))

    # ----------------------------------------------------------------- scoring
    @staticmethod
    def _score(findings) -> int:
        score = 100
        for f in findings:
            if f.severity == "critical":
                score -= 22
            elif f.severity == "warning":
                score -= 9
        return max(0, min(100, score))

    @staticmethod
    def _summary(findings, limited) -> str:
        crit = [f for f in findings if f.severity == "critical"]
        warn = [f for f in findings if f.severity == "warning"]
        if not crit and not warn:
            text = "Your computer is performing normally. No sustained resource problems were found."
        else:
            items = [f.title for f in crit + warn][:3]
            n = len(crit) + len(warn)
            text = f"{n} issue{'s' if n != 1 else ''} worth your attention: " + "; ".join(items) + "."
        if limited:
            text += " (Preliminary result: based on a very short measurement window.)"
        return text
