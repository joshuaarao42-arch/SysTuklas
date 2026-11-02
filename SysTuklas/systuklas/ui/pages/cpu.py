from __future__ import annotations

import customtkinter as ctk
import psutil

from ...core.formatting import fmt_freq
from ..theme import COLORS, font, usage_color
from ..widgets import Card, LiveChart, RankList, ReflowFrame, StatCard, cfg
from .base import BasePage


class CPUPage(BasePage):
    def __init__(self, master, app):
        super().__init__(master, app, "CPU Performance", "Utilization, frequency and per-core load", scrollable=True)
        c = self.content
        row = ReflowFrame(c, min_width=230)
        row.pack(fill="x")
        self.util = StatCard(row, "Utilization", COLORS["accent"])
        self.freq = StatCard(row, "Frequency", COLORS["purple"])
        self.cores = StatCard(row, "Cores and threads", show_bar=False)
        self.temp = StatCard(row, "Temperature", show_bar=False)
        for w in (self.util, self.freq, self.cores, self.temp):
            row.add(w)

        charts = ReflowFrame(c, min_width=440)
        charts.pack(fill="x", pady=(4, 0))
        c1 = Card(charts, "CPU usage — last 2 minutes")
        self.usage_chart = LiveChart(c1.body, [("cpu", "CPU %", COLORS["accent"])])
        self.usage_chart.pack(fill="both", expand=True, padx=8, pady=8)
        c2 = Card(charts, "Clock speed (MHz)")
        self.freq_chart = LiveChart(c2.body, [("f", "Current", COLORS["purple"])], min_top=1000)
        self.freq_chart.pack(fill="both", expand=True, padx=8, pady=8)
        charts.add(c1)
        charts.add(c2)

        pc = Card(c, "Load per logical processor")
        pc.pack(fill="x", pady=(10, 0), padx=5)
        self.core_flow = ReflowFrame(pc.body, min_width=150, gap=8)
        self.core_flow.pack(fill="x", padx=8, pady=(6, 12))
        self.tiles = []
        for i in range(psutil.cpu_count() or 1):
            tile = ctk.CTkFrame(self.core_flow, fg_color=COLORS["card_alt"], corner_radius=10)
            top = ctk.CTkFrame(tile, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(8, 2))
            ctk.CTkLabel(top, text=f"Thread {i}", font=font(11), text_color=COLORS["muted"]).pack(side="left")
            val = ctk.CTkLabel(top, text="0%", font=font(11, "bold"))
            val.pack(side="right")
            bar = ctk.CTkProgressBar(tile, height=6, corner_radius=3, fg_color=COLORS["border"])
            bar.set(0)
            bar.pack(fill="x", padx=10, pady=(0, 10))
            self.core_flow.add(tile)
            self.tiles.append((val, bar))

        self.top = RankList(c, "Programs using the most CPU right now")
        self.top.pack(fill="x", pady=(10, 12), padx=5)

    def refresh(self):
        s = self.monitor.latest
        if not s:
            return
        hist = self.monitor.get_history(120)
        cpus = [h.cpu for h in hist]
        last60 = cpus[-60:]
        self.util.update_values(f"{s.cpu:.0f}%", f"1-min average {sum(last60) / len(last60):.0f}% • peak {max(last60):.0f}%",
                                s.cpu, usage_color(s.cpu))
        if s.freq_current:
            pct = s.freq_current / s.freq_max * 100 if s.freq_max else None
            self.freq.update_values(fmt_freq(s.freq_current), f"Maximum {fmt_freq(s.freq_max)}" if s.freq_max else "Maximum not reported", pct)
        else:
            self.freq.update_values("N/A", "Frequency is not reported by this system", 0)
        d = self.app.hw.data
        self.cores.update_values(f"{d['physical_cores']} / {d['logical_cores']}", "physical cores / logical threads")
        if s.temperature is not None:
            self.temp.update_values(f"{s.temperature:.0f} °C", "Hottest sensor reading")
        else:
            self.temp.update_values("Not available", "No sensor available")
        self.usage_chart.update_data({"cpu": cpus}, ymax=100)
        self.freq_chart.update_data({"f": [h.freq_current or 0 for h in hist]})
        for (val, bar), pct in zip(self.tiles, s.per_core):
            step = round(pct)
            if getattr(bar, "_step", None) != step:
                bar._step = step
                val.configure(text=f"{step}%")
                bar.set(step / 100)
                cfg(bar, progress_color=usage_color(pct))
        top = sorted(self.procs.get_rows(), key=lambda r: r["cpu"], reverse=True)[:5]
        self.top.update_rows([(r["name"], f"{r['cpu']:.1f}%") for r in top])
