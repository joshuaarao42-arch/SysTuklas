from __future__ import annotations

import customtkinter as ctk

from ...core.formatting import fmt_bytes
from ..theme import COLORS, font, usage_color
from ..widgets import Card, DataTable, LiveChart, ReflowFrame, StatCard, StatusBadge
from .base import BasePage


class MemoryPage(BasePage):
    def __init__(self, master, app):
        super().__init__(master, app, "Memory Analyzer", "RAM, swap and the applications using the most memory",
                         scrollable=True)
        self.badge = StatusBadge(self.actions, "Collecting…", COLORS["muted"])
        self.badge.pack()
        c = self.content
        row = ReflowFrame(c, min_width=230)
        row.pack(fill="x")
        self.total = StatCard(row, "Installed memory", show_bar=False)
        self.used = StatCard(row, "In use", COLORS["purple"])
        self.avail = StatCard(row, "Available", COLORS["good"], show_bar=False)
        self.swap = StatCard(row, "Swap / page file", COLORS["cyan"])
        for w in (self.total, self.used, self.avail, self.swap):
            row.add(w)

        cc = Card(c, "Memory and swap usage — last 2 minutes")
        cc.pack(fill="x", pady=(10, 0), padx=5)
        self.chart = LiveChart(cc.body, [("ram", "Memory %", COLORS["purple"]), ("swap", "Swap %", COLORS["cyan"])])
        self.chart.pack(fill="both", expand=True, padx=8, pady=8)

        tc = Card(c, "Applications by memory use (all processes of an app combined)")
        tc.pack(fill="x", pady=(10, 12), padx=5)
        self.table = DataTable(tc.body, [
            {"key": "name", "title": "Application", "width": 240},
            {"key": "count", "title": "Processes", "width": 80, "anchor": "e", "numeric": True},
            {"key": "mem", "title": "Memory", "width": 110, "anchor": "e", "numeric": True},
            {"key": "pct", "title": "% of RAM", "width": 90, "anchor": "e", "numeric": True},
            {"key": "cpu", "title": "CPU %", "width": 80, "anchor": "e", "numeric": True},
        ], height=12)
        self.table.pack(fill="x", padx=10, pady=(6, 12))
        self.table.set_sort("mem", True)
        self._ver = -1

    def refresh(self):
        s = self.monitor.latest
        if not s:
            return
        self.total.update_values(fmt_bytes(s.ram_total), "Physical RAM")
        self.used.update_values(fmt_bytes(s.ram_used), f"{s.ram_percent:.0f}% of RAM", s.ram_percent, usage_color(s.ram_percent))
        self.avail.update_values(fmt_bytes(s.ram_available), "Free for new programs")
        if s.swap_total:
            self.swap.update_values(f"{fmt_bytes(s.swap_used)}", f"of {fmt_bytes(s.swap_total)} ({s.swap_percent:.0f}%)",
                                    s.swap_percent, usage_color(s.swap_percent))
        else:
            self.swap.update_values("None", "No swap / page file configured", 0)
        hist = self.monitor.get_history(120)
        self.chart.update_data({"ram": [h.ram_percent for h in hist], "swap": [h.swap_percent for h in hist]}, ymax=100)
        recent = [h.ram_percent for h in hist[-30:]]
        avg = sum(recent) / len(recent)
        if avg >= 85:
            self.badge.set("High memory pressure", COLORS["bad"])
        elif avg >= 70:
            self.badge.set("Elevated", COLORS["warn"])
        else:
            self.badge.set("Healthy", COLORS["good"])
        if self.procs.version != self._ver:
            self._ver = self.procs.version
            apps = sorted(self.procs.get_apps(), key=lambda a: a["rss"], reverse=True)[:40]
            self.table.set_rows([{
                "iid": a["name"].lower(),
                "values": [a["name"], a["count"], fmt_bytes(a["rss"]), f"{a['rss'] / s.ram_total * 100:.1f}%", f"{a['cpu']:.1f}"],
                "sort": [a["name"].lower(), a["count"], a["rss"], a["rss"], a["cpu"]],
            } for a in apps])
