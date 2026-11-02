from __future__ import annotations

import customtkinter as ctk

from ...core.formatting import fmt_bytes
from ..theme import COLORS, font, usage_color
from ..utils import choose_unit
from ..widgets import Card, DataTable, LiveChart, ReflowFrame, cfg
from .base import BasePage


class StoragePage(BasePage):
    def __init__(self, master, app):
        super().__init__(master, app, "Storage Analyzer", "Drive capacity, activity and health", scrollable=True)
        c = self.content
        self.drive_flow = ReflowFrame(c, min_width=300)
        self.drive_flow.pack(fill="x")
        self._cards: dict = {}
        self._mounts: tuple = ()

        cc = Card(c, "Disk activity — last 2 minutes")
        cc.pack(fill="x", pady=(10, 0), padx=5)
        self.io_note = ctk.CTkLabel(cc.body, text="", font=font(11), text_color=COLORS["muted"], anchor="w")
        self.io_note.pack(fill="x", padx=16)
        self.chart = LiveChart(cc.body, [("r", "Read", COLORS["accent"]), ("w", "Write", COLORS["warn"])])
        self.chart.pack(fill="both", expand=True, padx=8, pady=8)

        dc = Card(c, "Drive details")
        dc.pack(fill="x", pady=(10, 0), padx=5)
        self.table = DataTable(dc.body, [
            {"key": "dev", "title": "Drive", "width": 120},
            {"key": "mp", "title": "Mount point", "width": 120},
            {"key": "fs", "title": "File system", "width": 90},
            {"key": "total", "title": "Capacity", "width": 100, "anchor": "e", "numeric": True},
            {"key": "used", "title": "Used", "width": 100, "anchor": "e", "numeric": True},
            {"key": "free", "title": "Free", "width": 100, "anchor": "e", "numeric": True},
            {"key": "pct", "title": "Used %", "width": 70, "anchor": "e", "numeric": True},
        ], height=5)
        self.table.pack(fill="x", padx=10, pady=(6, 12))

        hc = Card(c, "Physical disk health (as reported by the operating system)")
        hc.pack(fill="x", pady=(10, 12), padx=5)
        self.health_note = ctk.CTkLabel(hc.body, text="Detecting drives…", font=font(12), text_color=COLORS["muted"],
                                        anchor="w", justify="left", wraplength=700)
        self.health_note.pack(fill="x", padx=16, pady=(4, 4))
        self.health = DataTable(hc.body, [
            {"key": "name", "title": "Drive", "width": 240},
            {"key": "type", "title": "Type", "width": 90},
            {"key": "health", "title": "Health", "width": 100},
            {"key": "status", "title": "Status", "width": 100},
            {"key": "size", "title": "Size", "width": 100, "anchor": "e", "numeric": True},
        ], height=3)
        self.health.pack(fill="x", padx=10, pady=(0, 12))
        self._health_done = False

    def _sync_cards(self, disks: list):
        mounts = tuple(d["mountpoint"] for d in disks)
        if mounts != self._mounts:
            for w in self._cards.values():
                w["card"].destroy()
            self.drive_flow._items.clear()
            self._cards = {}
            for d in disks:
                card = Card(self.drive_flow, f"{d['mountpoint']}  •  {d['fstype']}")
                big = ctk.CTkLabel(card.body, text="", font=font(26, "bold"), anchor="w")
                big.pack(fill="x", padx=16, pady=(2, 0))
                sub = ctk.CTkLabel(card.body, text="", font=font(12), text_color=COLORS["muted"], anchor="w")
                sub.pack(fill="x", padx=16)
                bar = ctk.CTkProgressBar(card.body, height=10, corner_radius=5, fg_color=COLORS["card_alt"])
                bar.set(0)
                bar.pack(fill="x", padx=16, pady=(8, 14))
                self._cards[d["mountpoint"]] = {"card": card, "big": big, "sub": sub, "bar": bar}
                self.drive_flow.add(card)
            self._mounts = mounts
        for d in disks:
            w = self._cards.get(d["mountpoint"])
            if not w:
                continue
            col = usage_color(d["percent"])
            cfg(w["big"], text=f"{fmt_bytes(d['free'])} free")
            cfg(w["sub"], text=f"{fmt_bytes(d['used'])} used of {fmt_bytes(d['total'])} ({d['percent']:.0f}%)")
            if w.get("pct") != round(d["percent"]):
                w["pct"] = round(d["percent"])
                w["bar"].set(d["percent"] / 100)
            cfg(w["bar"], progress_color=col)

    def refresh(self):
        disks = self.monitor.get_disks()
        self._sync_cards(disks)
        self.table.set_rows([{
            "iid": d["mountpoint"],
            "values": [d["device"], d["mountpoint"], d["fstype"], fmt_bytes(d["total"]), fmt_bytes(d["used"]),
                       fmt_bytes(d["free"]), f"{d['percent']:.0f}%"],
            "sort": [d["device"], d["mountpoint"], d["fstype"], d["total"], d["used"], d["free"], d["percent"]],
        } for d in disks])

        hist = self.monitor.get_history(120)
        if hist:
            if not self.monitor.disk_io_supported:
                self.io_note.configure(text="Read/write counters are not available on this system.")
            div, unit = choose_unit(max(max(h.disk_read_bps, h.disk_write_bps) for h in hist))
            cfg(self.io_note, text=f"Now: read {hist[-1].disk_read_bps / div:.1f} {unit} • write {hist[-1].disk_write_bps / div:.1f} {unit}"
                                   if self.monitor.disk_io_supported else "Read/write counters are not available on this system.")
            self.chart.update_data({"r": [h.disk_read_bps / div for h in hist], "w": [h.disk_write_bps / div for h in hist]},
                                   ylabel=unit)

        hw = self.app.hw
        if hw.disks_probed and not self._health_done:
            self._health_done = True
            pd = hw.physical_disks or []
            if pd:
                self.health_note.configure(
                    text="Health comes from the status Windows reports. Detailed SMART attributes need vendor tools "
                         "and are not read by SysTuklas.")
                self.health.set_rows([{
                    "iid": f"{i}", "values": [p["name"], p["type"], p["health"], p["status"], fmt_bytes(p["size"])],
                    "sort": [p["name"], p["type"], p["health"], p["status"], p["size"] or 0],
                } for i, p in enumerate(pd)])
            else:
                self.health_note.configure(
                    text="Health information is not available on this system (it is read through Windows PowerShell). "
                         "Free space and activity above are still measured.")
