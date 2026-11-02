from __future__ import annotations

import customtkinter as ctk

from ...core.formatting import fmt_bytes, fmt_rate
from ..theme import COLORS, font
from ..utils import choose_unit
from ..widgets import Card, DataTable, LiveChart, ReflowFrame, StatCard
from .base import BasePage


class NetworkPage(BasePage):
    def __init__(self, master, app):
        super().__init__(master, app, "Network Monitor", "Live speeds and data transferred", scrollable=True)
        c = self.content
        row = ReflowFrame(c, min_width=230)
        row.pack(fill="x")
        self.down = StatCard(row, "Download speed", COLORS["good"], show_bar=False)
        self.up = StatCard(row, "Upload speed", COLORS["accent"], show_bar=False)
        self.tot_down = StatCard(row, "Downloaded", COLORS["good"], show_bar=False)
        self.tot_up = StatCard(row, "Uploaded", COLORS["accent"], show_bar=False)
        for w in (self.down, self.up, self.tot_down, self.tot_up):
            row.add(w)

        cc = Card(c, "Throughput — last 2 minutes")
        cc.pack(fill="x", pady=(10, 0), padx=5)
        self.chart = LiveChart(cc.body, [("d", "Download", COLORS["good"]), ("u", "Upload", COLORS["accent"])])
        self.chart.pack(fill="both", expand=True, padx=8, pady=8)

        ic = Card(c, "Network adapters")
        ic.pack(fill="x", pady=(10, 12), padx=5)
        self.conn_label = ctk.CTkLabel(ic.body, text="", font=font(12), text_color=COLORS["muted"], anchor="w")
        self.conn_label.pack(fill="x", padx=16, pady=(2, 4))
        self.table = DataTable(ic.body, [
            {"key": "name", "title": "Adapter", "width": 200},
            {"key": "state", "title": "State", "width": 70},
            {"key": "speed", "title": "Link speed", "width": 90, "anchor": "e", "numeric": True},
            {"key": "ip", "title": "IPv4 address", "width": 130},
            {"key": "sent", "title": "Sent", "width": 100, "anchor": "e", "numeric": True},
            {"key": "recv", "title": "Received", "width": 100, "anchor": "e", "numeric": True},
        ], height=7)
        self.table.pack(fill="x", padx=10, pady=(0, 12))

    def refresh(self):
        s = self.monitor.latest
        if not s:
            return
        self.down.update_values(fmt_rate(s.net_down_bps), f"Peak this session: {fmt_rate(self.monitor.peak_down)}")
        self.up.update_values(fmt_rate(s.net_up_bps), f"Peak this session: {fmt_rate(self.monitor.peak_up)}")
        sess_sent, sess_recv = self.monitor.session_totals()
        self.tot_down.update_values(fmt_bytes(sess_recv), f"This session • {fmt_bytes(s.net_recv_total)} since boot")
        self.tot_up.update_values(fmt_bytes(sess_sent), f"This session • {fmt_bytes(s.net_sent_total)} since boot")
        hist = self.monitor.get_history(120)
        div, unit = choose_unit(max(max(h.net_down_bps, h.net_up_bps) for h in hist))
        self.chart.update_data({"d": [h.net_down_bps / div for h in hist], "u": [h.net_up_bps / div for h in hist]},
                               ylabel=unit)
        conns = self.monitor.connections
        self.conn_label.configure(text=f"Established connections: {conns}" if conns is not None
                                  else "Connection count is not available (requires elevated permissions on this system).")
        rows = self.monitor.get_interfaces()
        self.table.set_rows([{
            "iid": r["name"],
            "values": [r["name"], "Up" if r["up"] else "Down", f"{r['speed']} Mbps" if r["speed"] else "—",
                       r["ipv4"] or "—", fmt_bytes(r["sent"]), fmt_bytes(r["recv"])],
            "sort": [r["name"].lower(), int(r["up"]), r["speed"], r["ipv4"], r["sent"], r["recv"]],
        } for r in rows])
