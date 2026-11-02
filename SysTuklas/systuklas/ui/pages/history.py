from __future__ import annotations

import time
from tkinter import filedialog

import customtkinter as ctk

from ...core.exporter import export_history_csv
from ...core.formatting import fmt_bytes, fmt_duration, fmt_time
from ..dialogs import ask_confirm, export_report_dialog, show_message, view_report_dialog
from ..theme import COLORS, font, score_color
from ..utils import choose_unit, run_async
from ..widgets import Card, DataTable, HistoryChart, ReflowFrame, ScrollFrame, StatCard
from .base import BasePage

RANGES = {"1 hour": 3600, "6 hours": 21600, "24 hours": 86400, "7 days": 604800, "30 days": 2592000}
METRICS = ["Usage %", "Disk I/O", "Network"]


def _seg(master, values, command):
    return ctk.CTkSegmentedButton(master, values=values, command=command, fg_color=COLORS["card_alt"],
                                  selected_color=COLORS["accent"], selected_hover_color=COLORS["accent_dark"],
                                  unselected_color=COLORS["card_alt"], unselected_hover_color=COLORS["border"],
                                  text_color=COLORS["text"])


class HistoryPage(BasePage):
    def __init__(self, master, app):
        super().__init__(master, app, "Performance History", "Long-term trends saved in a local SQLite database")
        self.db = app.db
        self._token = 0
        self._last_load = 0.0
        self._rows: list = []
        tabs = ctk.CTkTabview(self.content, fg_color=COLORS["card"], segmented_button_selected_color=COLORS["accent"],
                              segmented_button_unselected_color=COLORS["card_alt"])
        tabs.pack(fill="both", expand=True)
        self.tabs = tabs
        perf = tabs.add("Performance")
        rep = tabs.add("Saved reports")
        self._build_perf(perf)
        self._build_reports(rep)

    # ------------------------------------------------------------ performance
    def _build_perf(self, tab):
        sf = ScrollFrame(tab)
        sf.pack(fill="both", expand=True)
        scroll = sf.inner
        ctl = ctk.CTkFrame(scroll, fg_color="transparent")
        ctl.pack(fill="x", pady=(2, 8))
        self.range_btn = _seg(ctl, list(RANGES), lambda v: self.load())
        self.range_btn.set("1 hour")
        self.range_btn.pack(side="left")
        self.metric_btn = _seg(ctl, METRICS, lambda v: self._render())
        self.metric_btn.set("Usage %")
        self.metric_btn.pack(side="left", padx=12)
        self.rec_switch = ctk.CTkSwitch(ctl, text="Record history", command=self._toggle_rec)
        if self.app.recorder.enabled:
            self.rec_switch.select()
        self.rec_switch.pack(side="right")

        sums = ReflowFrame(scroll, min_width=190)
        sums.pack(fill="x")
        self.s_cpu = StatCard(sums, "CPU (avg / peak)", COLORS["accent"], show_bar=False)
        self.s_ram = StatCard(sums, "Memory (avg / peak)", COLORS["purple"], show_bar=False)
        self.s_disk = StatCard(sums, "System drive (avg / peak)", COLORS["cyan"], show_bar=False)
        self.s_n = StatCard(sums, "Recorded data", COLORS["good"], show_bar=False)
        for w in (self.s_cpu, self.s_ram, self.s_disk, self.s_n):
            sums.add(w)

        cc = Card(scroll)
        cc.pack(fill="x", pady=(8, 6), padx=5)
        self.chart = HistoryChart(cc.body, height=300)
        self.chart.pack(fill="both", expand=True, padx=8, pady=8)

        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        for text, cmd, danger in (("Refresh", self.load, False), ("Export CSV…", self.export_csv, False),
                                  ("Save chart as PNG…", self.save_png, False), ("Clear history…", self.clear, True)):
            ctk.CTkButton(row, text=text, width=130, command=cmd,
                          fg_color=COLORS["bad"] if danger else COLORS["card_alt"],
                          hover_color="#DC2626" if danger else COLORS["border"],
                          text_color="#0B0F14" if danger else COLORS["text"]).pack(side="left", padx=(0, 8))

    def _toggle_rec(self):
        self.app.recorder.set_enabled(bool(self.rec_switch.get()))

    def on_show(self):
        self.load()
        self._load_reports()

    def refresh(self):
        if time.time() - self._last_load > 30:
            self.load()

    def load(self):
        self._last_load = time.time()
        self._token += 1
        token = self._token
        since = time.time() - RANGES[self.range_btn.get()]

        def work():
            return self.db.query_series(since, None, 600), self.db.summary(since)

        run_async(self, work, lambda res, err: self._loaded(token, res, err))

    def _loaded(self, token, res, err):
        if token != self._token:
            return
        if err:
            self.chart.show_message(f"Could not read history: {err}")
            return
        self._rows, summ = res
        n = summ["n"]
        if n:
            self.s_cpu.update_values(f"{summ['cpu_avg']:.0f}%", f"peak {summ['cpu_peak']:.0f}%")
            self.s_ram.update_values(f"{summ['ram_avg']:.0f}%", f"peak {summ['ram_peak']:.0f}%")
            self.s_disk.update_values(f"{summ['disk_avg']:.0f}%", f"peak {summ['disk_peak']:.0f}%")
            self.s_n.update_values(f"{n:,}", f"samples • {fmt_duration(summ['span_seconds'])} of data")
        else:
            for card in (self.s_cpu, self.s_ram, self.s_disk):
                card.update_values("—", "no data in this period")
            self.s_n.update_values("0", "samples")
        self._render()

    def _render(self):
        rows = self._rows
        times = [r["ts"] for r in rows]
        metric = self.metric_btn.get()
        if metric == "Usage %":
            self.chart.plot(times, [
                {"label": "CPU", "color": COLORS["accent"], "values": [r["cpu"] for r in rows]},
                {"label": "Memory", "color": COLORS["purple"], "values": [r["ram"] for r in rows]},
                {"label": "System drive", "color": COLORS["cyan"], "values": [r["disk"] for r in rows]},
            ], ylabel="%", ymax=100)
        else:
            a, b, la, lb = (("disk_read", "disk_write", "Read", "Write") if metric == "Disk I/O"
                            else ("net_down", "net_up", "Download", "Upload"))
            peak = max((max(r[a] or 0, r[b] or 0) for r in rows), default=0)
            div, unit = choose_unit(peak)
            self.chart.plot(times, [
                {"label": la, "color": COLORS["good"], "values": [(r[a] or 0) / div for r in rows]},
                {"label": lb, "color": COLORS["warn"], "values": [(r[b] or 0) / div for r in rows]},
            ], ylabel=unit)

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self.winfo_toplevel(), defaultextension=".csv",
                                            initialfile="systuklas-history", filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        since = time.time() - RANGES[self.range_btn.get()]
        run_async(self, lambda: export_history_csv(self.db.raw_samples(since), path),
                  lambda n, err: show_message(self, "Export failed", str(err), "error") if err else
                  show_message(self, "History exported", f"{n:,} records saved to:\n{path}", "ok"))

    def save_png(self):
        path = filedialog.asksaveasfilename(parent=self.winfo_toplevel(), defaultextension=".png",
                                            initialfile="systuklas-chart", filetypes=[("PNG image", "*.png")])
        if not path:
            return
        try:
            self.chart.save_png(path)
            show_message(self, "Chart saved", f"Saved to:\n{path}", "ok")
        except Exception as exc:  # noqa: BLE001
            show_message(self, "Could not save chart", str(exc), "error")

    def clear(self):
        if not ask_confirm(self, "Clear performance history?",
                           "All recorded CPU, memory, disk and network history will be permanently deleted.\n"
                           "Saved diagnostic reports are kept.", "Delete history", danger=True):
            return
        run_async(self, self.db.clear_history, lambda r, e: (show_message(self, "Error", str(e), "error") if e else self.load()))

    # ---------------------------------------------------------------- reports
    def _build_reports(self, tab):
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", pady=(2, 8))
        for text, cmd, danger in (("View", self.view_report, False), ("Export…", self.export_report, False),
                                  ("Delete", self.delete_report, True)):
            ctk.CTkButton(row, text=text, width=100, command=cmd,
                          fg_color=COLORS["bad"] if danger else COLORS["accent"],
                          hover_color="#DC2626" if danger else COLORS["accent_dark"],
                          text_color="#0B0F14").pack(side="left", padx=(0, 8))
        self.rep_count = ctk.CTkLabel(row, text="", font=font(12), text_color=COLORS["muted"])
        self.rep_count.pack(side="right")
        self.rep_table = DataTable(tab, [
            {"key": "when", "title": "Date", "width": 150},
            {"key": "score", "title": "Score", "width": 60, "anchor": "e", "numeric": True},
            {"key": "label", "title": "Status", "width": 110},
            {"key": "issues", "title": "Issues", "width": 70, "anchor": "e", "numeric": True},
            {"key": "summary", "title": "Summary", "width": 420},
        ], height=12, on_double=self.view_report)
        self.rep_table.pack(fill="both", expand=True)

    def _load_reports(self):
        def work():
            return self.db.list_reports()

        def done(rows, err):
            if err:
                return
            self.rep_count.configure(text=f"{len(rows)} saved report(s)")
            self.rep_table.set_rows([{
                "iid": str(r["id"]),
                "values": [fmt_time(r["ts"]), r["score"], r["label"], (r["critical"] or 0) + (r["warning"] or 0), r["summary"]],
                "sort": [r["ts"], r["score"], r["label"], (r["critical"] or 0) + (r["warning"] or 0), r["summary"]],
            } for r in rows])
            self.rep_table.set_sort("when", True)

        run_async(self, work, done)

    def _selected_report(self):
        iid = self.rep_table.selected()
        if iid is None:
            show_message(self, "No report selected", "Select a report in the list first.", "info")
            return None
        return self.db.get_report(int(iid))

    def view_report(self):
        r = self._selected_report()
        if r:
            view_report_dialog(self, r)

    def export_report(self):
        r = self._selected_report()
        if r:
            export_report_dialog(self, r)

    def delete_report(self):
        iid = self.rep_table.selected()
        if iid is None:
            show_message(self, "No report selected", "Select a report in the list first.", "info")
            return
        if ask_confirm(self, "Delete report?", "This saved report will be permanently deleted.", "Delete", danger=True):
            self.db.delete_report(int(iid))
            self._load_reports()
