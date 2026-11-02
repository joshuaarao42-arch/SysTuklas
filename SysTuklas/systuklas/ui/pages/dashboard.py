from __future__ import annotations

import time

import customtkinter as ctk

from ...core.formatting import fmt_bytes, fmt_duration, fmt_freq, fmt_rate, fmt_time
from ..theme import COLORS, font, score_color, usage_color
from ..widgets import Card, KeyValueCard, LiveChart, RankList, ReflowFrame, StatCard, cfg
from .base import BasePage


class DashboardPage(BasePage):
    def __init__(self, master, app):
        super().__init__(master, app, "Dashboard", "Live overview of your computer's performance", scrollable=True)
        c = self.content
        stats = ReflowFrame(c, min_width=220)
        stats.pack(fill="x")
        self.cpu = StatCard(stats, "CPU", COLORS["accent"])
        self.ram = StatCard(stats, "Memory", COLORS["purple"])
        self.disk = StatCard(stats, "System drive", COLORS["cyan"])
        self.net = StatCard(stats, "Network", COLORS["good"], show_bar=False)
        for w in (self.cpu, self.ram, self.disk, self.net):
            stats.add(w)

        mid = ReflowFrame(c, min_width=440)
        mid.pack(fill="x", pady=(4, 0))
        chart_card = Card(mid, "CPU and memory — last 2 minutes")
        self.chart = LiveChart(chart_card.body, [("cpu", "CPU", COLORS["accent"]), ("ram", "Memory", COLORS["purple"])])
        self.chart.pack(fill="both", expand=True, padx=8, pady=8)
        self.info = KeyValueCard(mid, "This computer", ["Computer", "Operating system", "Processor", "Cores / threads",
                                                        "Memory", "Graphics", "Uptime", "Last boot"])
        mid.add(chart_card)
        mid.add(self.info)

        bot = ReflowFrame(c, min_width=290)
        bot.pack(fill="x", pady=(4, 12))
        self.top_cpu = RankList(bot, "Top CPU consumers")
        self.top_mem = RankList(bot, "Top memory consumers")
        self.diag = Card(bot, "Diagnostics")
        self.diag_score = ctk.CTkLabel(self.diag.body, text="—", font=font(30, "bold"), anchor="w")
        self.diag_score.pack(fill="x", padx=16, pady=(2, 0))
        self.diag_text = ctk.CTkLabel(self.diag.body, text="No scan yet", font=font(12), text_color=COLORS["muted"],
                                      anchor="w", justify="left", wraplength=240)
        self.diag_text.pack(fill="x", padx=16)
        ctk.CTkButton(self.diag.body, text="Run diagnostic scan", command=lambda: app.show_page("diagnostics", run=True)
                      ).pack(anchor="w", padx=16, pady=(10, 14))
        for w in (self.top_cpu, self.top_mem, self.diag):
            bot.add(w)

    def on_show(self):
        d = self.app.hw.data
        self.info.set("Computer", d["hostname"])
        self.info.set("Operating system", f"{d['os']} ({d['machine']})")
        self.info.set("Processor", d["cpu_name"])
        self.info.set("Cores / threads", f"{d['physical_cores']} physical / {d['logical_cores']} logical")
        self.info.set("Memory", fmt_bytes(d["ram_total"]))
        self.info.set("Last boot", fmt_time(d["boot_time"]))

    def refresh(self):
        s = self.monitor.latest
        if not s:
            return
        self.cpu.update_values(f"{s.cpu:.0f}%", f"{self.monitor.logical_cores} thread{'s' if self.monitor.logical_cores != 1 else ''} • {fmt_freq(s.freq_current)}",
                               s.cpu, usage_color(s.cpu))
        self.ram.update_values(f"{s.ram_percent:.0f}%", f"{fmt_bytes(s.ram_used)} of {fmt_bytes(s.ram_total)}",
                               s.ram_percent, usage_color(s.ram_percent))
        self.disk.update_values(f"{s.disk_percent:.0f}%", f"{fmt_bytes(s.disk_free)} free of {fmt_bytes(s.disk_total)}",
                                s.disk_percent, usage_color(s.disk_percent))
        self.net.update_values(f"↓ {fmt_rate(s.net_down_bps)}", f"↑ {fmt_rate(s.net_up_bps)}")
        hist = self.monitor.get_history(120)
        self.chart.update_data({"cpu": [h.cpu for h in hist], "ram": [h.ram_percent for h in hist]}, ymax=100)
        self.info.set("Uptime", fmt_duration(self.app.hw.uptime()))
        self.info.set("Graphics", self.app.hw.gpu)

        rows = self.procs.get_rows()
        top_cpu = sorted(rows, key=lambda r: r["cpu"], reverse=True)[:5]
        self.top_cpu.update_rows([(r["name"], f"{r['cpu']:.1f}%") for r in top_cpu])
        apps = sorted(self.procs.get_apps(), key=lambda a: a["rss"], reverse=True)[:5]
        self.top_mem.update_rows([(a["name"], fmt_bytes(a["rss"])) for a in apps])

        rep = self.app.last_report
        if rep:
            cfg(self.diag_score, text=f"{rep.health_score}/100  {rep.health_label}",
                text_color=score_color(rep.health_score))
            cfg(self.diag_text, text=f"Last scan {fmt_time(rep.generated_at)}\n{rep.summary}")
