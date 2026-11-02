from __future__ import annotations

import time

import customtkinter as ctk

from ...core.diagnostics import DISCLAIMER, SEVERITY_LABELS
from ...core.formatting import fmt_duration, fmt_time
from ..dialogs import export_report_dialog, show_message
from ..theme import COLORS, SEVERITY_COLORS, font, score_color
from ..utils import auto_wrap, run_async
from ..widgets import Card, KeyValueCard, StatusBadge
from .base import BasePage


class FindingCard(ctk.CTkFrame):
    def __init__(self, master, f):
        super().__init__(master, fg_color=COLORS["card"], corner_radius=8)
        color = SEVERITY_COLORS[f.severity]
        ctk.CTkFrame(self, width=6, height=10, fg_color=color, corner_radius=3).pack(side="left", fill="y", padx=(8, 0), pady=8)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x")
        StatusBadge(top, SEVERITY_LABELS[f.severity], color).pack(side="left")
        ctk.CTkLabel(top, text=f"   {f.category}", font=font(11), text_color=COLORS["muted"]).pack(side="left")
        labels = [ctk.CTkLabel(body, text=f.title, font=font(15, "bold"), anchor="w", justify="left")]
        labels.append(ctk.CTkLabel(body, text=f.detail, font=font(12), anchor="w", justify="left",
                                   text_color=COLORS["text"]))
        if f.recommendation:
            labels.append(ctk.CTkLabel(body, text="→ " + f.recommendation, font=font(12), anchor="w", justify="left",
                                       text_color=COLORS["accent"]))
        for lbl, pad in zip(labels, ((8, 2), (0, 4), (0, 0))):
            lbl.pack(fill="x", pady=pad)
            auto_wrap(lbl, self, pad=70)


class DiagnosticsPage(BasePage):
    def __init__(self, master, app):
        super().__init__(master, app, "Diagnostic Engine", "Analyses measured data and explains what it means",
                         scrollable=True)
        self._scanning = False
        c = self.content

        top = Card(c)
        top.pack(fill="x", padx=5, pady=(0, 8))
        row = ctk.CTkFrame(top.body, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=14)
        row.grid_columnconfigure(1, weight=1)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw", padx=(0, 20))
        ctk.CTkLabel(left, text="HEALTH SCORE", font=font(11, "bold"), text_color=COLORS["muted"]).pack(anchor="w")
        self.score = ctk.CTkLabel(left, text="—", font=font(46, "bold"))
        self.score.pack(anchor="w")
        self.badge = StatusBadge(left, "No scan yet", COLORS["muted"])
        self.badge.pack(anchor="w", pady=(2, 0))
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        self.summary = ctk.CTkLabel(right, text="Run a scan to analyse your computer's recent performance.",
                                    font=font(14), anchor="w", justify="left")
        self.summary.pack(fill="x")
        auto_wrap(self.summary, top, pad=280)
        self.when = ctk.CTkLabel(right, text="", font=font(12), text_color=COLORS["muted"], anchor="w")
        self.when.pack(fill="x", pady=(4, 8))
        btns = ctk.CTkFrame(right, fg_color="transparent")
        btns.pack(fill="x")
        self.scan_btn = ctk.CTkButton(btns, text="Run diagnostic scan", height=36, command=self.run_scan)
        self.scan_btn.pack(side="left")
        self.export_btn = ctk.CTkButton(btns, text="Export report…", height=36, fg_color=COLORS["card_alt"],
                                        hover_color=COLORS["border"], state="disabled", command=self.export)
        self.export_btn.pack(side="left", padx=8)
        self.progress = ctk.CTkProgressBar(right, mode="indeterminate", height=6)

        self.list = ctk.CTkFrame(c, fg_color="transparent")
        self.list.pack(fill="x", padx=5)
        self.measured = KeyValueCard(c, "What was measured", ["Measurements", "Time window", "CPU average / peak",
                                                              "Memory average / peak", "Memory available",
                                                              "Disk activity (avg)", "Download / upload (avg)", "Processes"])
        self.measured.pack(fill="x", padx=5, pady=(8, 0))
        self.notes = ctk.CTkLabel(c, text=DISCLAIMER, font=font(11), text_color=COLORS["muted"], anchor="w",
                                  justify="left")
        self.notes.pack(fill="x", padx=12, pady=(10, 16))
        auto_wrap(self.notes, c, pad=60)
        if app.last_report:
            self._show(app.last_report)

    def on_show(self):
        pass

    # ----- scan -----
    def run_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scan_btn.configure(state="disabled", text="Scanning…")
        self.progress.pack(fill="x", pady=(10, 0))
        self.progress.start()
        run_async(self, self._worker, self._done)

    def _worker(self):
        app = self.app
        ver = app.procs.version
        app.procs.request_refresh()
        t0 = time.time()
        while app.procs.version == ver and time.time() - t0 < 4:
            time.sleep(0.1)
        hw = app.hw
        system = dict(hw.data)
        system.update({"gpu": hw.gpu if hw.gpu != "Detecting…" else None, "uptime_seconds": hw.uptime()})
        stats = app.db.summary(time.time() - 86400)
        report = app.engine.analyze(
            samples=app.monitor.get_history(), processes=app.procs.get_rows(), disks=app.monitor.get_disks(),
            system=system, history_stats=stats, physical_disks=hw.physical_disks)
        app.db.save_report(report)
        return report

    def _done(self, report, err):
        self._scanning = False
        self.progress.stop()
        self.progress.pack_forget()
        self.scan_btn.configure(state="normal", text="Run diagnostic scan")
        if err or report is None:
            show_message(self, "Scan failed", f"The diagnostic scan could not complete:\n{err}", "error")
            return
        self.app.last_report = report
        self._show(report)

    def _show(self, r):
        self.score.configure(text=f"{r.health_score}", text_color=score_color(r.health_score))
        self.badge.set(r.health_label, score_color(r.health_score))
        self.summary.configure(text=r.summary)
        self.when.configure(text=f"Scan completed {fmt_time(r.generated_at)} • analysed {r.metrics.get('samples', 0)} "
                                 f"measurements over {fmt_duration(r.window_seconds)}")
        for w in self.list.winfo_children():
            w.destroy()
        for f in r.findings:
            FindingCard(self.list, f).pack(fill="x", pady=4)
        m = r.metrics
        self.measured.set("Measurements", m.get("samples", "—"))
        self.measured.set("Time window", m.get("window", "—"))
        self.measured.set("CPU average / peak", f"{m.get('cpu_avg', '—')}% / {m.get('cpu_peak', '—')}%")
        self.measured.set("Memory average / peak", f"{m.get('ram_avg', '—')}% / {m.get('ram_peak', '—')}%")
        self.measured.set("Memory available", m.get("ram_available", "—"))
        self.measured.set("Disk activity (avg)", m.get("disk_io_avg", "—"))
        self.measured.set("Download / upload (avg)", f"{m.get('net_down_avg', '—')} / {m.get('net_up_avg', '—')}")
        self.measured.set("Processes", m.get("processes", "—"))
        self.notes.configure(text="\n".join("• " + n for n in r.notes))
        self.export_btn.configure(state="normal")

    def export(self):
        if self.app.last_report:
            export_report_dialog(self, self.app.last_report)
