from __future__ import annotations

import customtkinter as ctk
import psutil

from ...core.formatting import fmt_bytes
from ...core.monitor import get_process_details, protection_level, terminate_process
from ..dialogs import BaseDialog, ask_confirm, show_message
from ..theme import COLORS, font
from ..utils import run_async
from ..widgets import DataTable, cfg
from .base import BasePage

SORT_OPTIONS = {"CPU usage": ("cpu", True), "Memory": ("mem", True), "Name (A–Z)": ("name", False),
                "PID": ("pid", False)}


class ProcessesPage(BasePage):
    def __init__(self, master, app):
        super().__init__(master, app, "Process Analyzer", "Search, sort and inspect everything that is running")
        bar = ctk.CTkFrame(self.content, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        self.search = ctk.CTkEntry(bar, placeholder_text="Search by name, PID or user…", width=300, height=34)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda e: self._update_table(force=True))
        ctk.CTkLabel(bar, text="Sort by", text_color=COLORS["muted"], font=font(12)).pack(side="left", padx=(14, 6))
        self.sort_menu = ctk.CTkOptionMenu(bar, values=list(SORT_OPTIONS), width=130, command=self._on_sort)
        self.sort_menu.pack(side="left")
        self.active_only = ctk.CTkSwitch(bar, text="Active only", command=lambda: self._update_table(force=True))
        self.active_only.pack(side="left", padx=16)
        ctk.CTkButton(bar, text="End process", width=110, fg_color=COLORS["bad"], hover_color="#DC2626",
                      text_color="#0B0F14", command=self.terminate_selected).pack(side="right")
        ctk.CTkButton(bar, text="Details", width=90, command=self.show_details).pack(side="right", padx=8)
        ctk.CTkButton(bar, text="Refresh", width=90, fg_color=COLORS["card_alt"], hover_color=COLORS["border"],
                      command=self.refresh_now).pack(side="right")

        self.table = DataTable(self.content, [
            {"key": "name", "title": "Name", "width": 230},
            {"key": "pid", "title": "PID", "width": 70, "anchor": "e", "numeric": True},
            {"key": "cpu", "title": "CPU %", "width": 80, "anchor": "e", "numeric": True},
            {"key": "mem", "title": "Memory", "width": 100, "anchor": "e", "numeric": True},
            {"key": "threads", "title": "Threads", "width": 70, "anchor": "e", "numeric": True},
            {"key": "status", "title": "Status", "width": 90},
            {"key": "user", "title": "User", "width": 140},
        ], height=16, on_double=self.show_details)
        self.table.pack(fill="both", expand=True)
        self.table.set_sort("cpu", True)
        self._ver = -1
        self._names: dict = {}
        foot = ctk.CTkFrame(self.content, fg_color="transparent")
        foot.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(foot, text="Tip: double-click a process to inspect it. Click a column header to sort.",
                     text_color=COLORS["muted"], font=font(11), anchor="w").pack(side="left")
        self.count = ctk.CTkLabel(foot, text="", text_color=COLORS["text"], font=font(12, "bold"))
        self.count.pack(side="right")

    # ----- data -----
    def on_show(self):
        self._update_table(force=True)

    def refresh(self):
        self._update_table()

    def refresh_now(self):
        self.procs.request_refresh()

    def _on_sort(self, choice: str):
        key, desc = SORT_OPTIONS[choice]
        self.table.set_sort(key, desc)

    def _update_table(self, force: bool = False):
        if not force and self.procs.version == self._ver:
            return
        self._ver = self.procs.version
        rows = self.procs.get_rows()
        q = self.search.get().strip().lower()
        if q:
            rows = [r for r in rows if q in r["name"].lower() or q in str(r["pid"]) or q in r["user"].lower()]
        if self.active_only.get():
            rows = [r for r in rows if r["cpu"] >= 0.1]
        self._names = {str(r["pid"]): r["name"] for r in rows}
        self.table.set_rows([{
            "iid": str(r["pid"]),
            "values": [r["name"], r["pid"], f"{r['cpu']:.1f}", fmt_bytes(r["rss"]) if r["rss"] else "—",
                       r["threads"], r["status"], r["user"]],
            "sort": [r["name"].lower(), r["pid"], r["cpu"], r["rss"], r["threads"], r["status"], r["user"].lower()],
        } for r in rows])
        total_cpu = sum(r["cpu"] for r in rows)
        cfg(self.count, text=f"{len(rows)} processes • {total_cpu:.1f}% CPU")

    # ----- actions -----
    def _selected(self):
        iid = self.table.selected()
        if iid is None:
            show_message(self, "No process selected", "Click a process in the list first.", "info")
            return None
        return int(iid), self._names.get(iid, "this process")

    def show_details(self):
        sel = self._selected()
        if not sel:
            return
        pid, name = sel
        run_async(self, lambda: get_process_details(pid), lambda res, err: self._details_ready(pid, name, res, err))

    def _details_ready(self, pid, name, res, err):
        if isinstance(err, psutil.NoSuchProcess):
            show_message(self, "Process ended", f"{name} (PID {pid}) is no longer running.", "info")
            return
        if err:
            show_message(self, "Cannot read process", f"Details are not available:\n{err}", "error")
            return
        ProcessDetailsDialog(self, name, pid, res)

    def terminate_selected(self):
        sel = self._selected()
        if not sel:
            return
        pid, name = sel
        level = protection_level(pid, name)
        if level == "blocked":
            show_message(self, "Protected process",
                         f"'{name}' (PID {pid}) is essential to the system or to SysTuklas itself and cannot be ended here.",
                         "warn")
            return
        msg = (f"End '{name}' (PID {pid})?\n\nAny unsaved work in this program will be lost.")
        if level == "critical":
            msg += ("\n\n⚠ This looks like an important system process. Ending it may make Windows unstable, "
                    "close your session or force a restart.")
        if not ask_confirm(self, "End process?", msg, "End process", danger=True):
            return
        run_async(self, lambda: terminate_process(pid), lambda res, err: self._terminated(pid, name, res, err))

    def _terminated(self, pid, name, res, err):
        if isinstance(err, psutil.NoSuchProcess):
            show_message(self, "Already closed", f"{name} had already ended.", "info")
        elif isinstance(err, psutil.AccessDenied):
            show_message(self, "Access denied",
                         f"Windows does not allow SysTuklas to end '{name}'.\nTry running SysTuklas as Administrator.",
                         "error")
        elif err:
            show_message(self, "Could not end process", str(err), "error")
        elif res is False:
            if ask_confirm(self, "Process did not exit",
                           f"'{name}' did not close when asked politely. Force it to stop?\n\nUnsaved data will be lost.",
                           "Force stop", danger=True):
                run_async(self, lambda: terminate_process(pid, force=True),
                          lambda r, e: show_message(self, "Force stop", "Process stopped." if not e and r else
                                                    f"Could not stop the process.{' ' + str(e) if e else ''}",
                                                    "ok" if not e and r else "error"))
        self.refresh_now()


class ProcessDetailsDialog(BaseDialog):
    def __init__(self, parent, name: str, pid: int, details: list):
        super().__init__(parent, f"{name} — details")
        self.resizable(True, True)
        box = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=14)
        box.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(box, text=name, font=font(18, "bold"), anchor="w").pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(box, text=f"Process ID {pid}", font=font(12), text_color=COLORS["muted"], anchor="w").pack(
            fill="x", padx=20, pady=(0, 6))
        scroll = ctk.CTkScrollableFrame(box, fg_color="transparent", width=560, height=380)
        scroll.pack(fill="both", expand=True, padx=8)
        scroll.grid_columnconfigure(1, weight=1)
        for i, (k, v) in enumerate(details):
            ctk.CTkLabel(scroll, text=k, font=font(12), text_color=COLORS["muted"], anchor="nw").grid(
                row=i, column=0, sticky="nw", padx=(10, 12), pady=4)
            ctk.CTkLabel(scroll, text=str(v), font=font(12), anchor="nw", justify="left", wraplength=360).grid(
                row=i, column=1, sticky="nw", padx=(0, 10), pady=4)
        self._text = "\n".join(f"{k}: {v}" for k, v in details)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=14)
        ctk.CTkButton(row, text="Close", width=100, command=self.close).pack(side="right")
        ctk.CTkButton(row, text="Copy", width=100, fg_color=COLORS["card_alt"], hover_color=COLORS["border"],
                      command=self._copy).pack(side="right", padx=8)
        self.present()

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._text)
