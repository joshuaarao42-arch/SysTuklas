"""Main window: sidebar navigation, page management and background services."""
from __future__ import annotations

import logging
import threading

import customtkinter as ctk

from ..core.database import Database, HistoryRecorder
from ..core.diagnostics import DiagnosticEngine
from ..core.monitor import HardwareInfo, ProcessSampler, SystemMonitor
from .icons import ctk_icon, pil_icon
from .pages.cpu import CPUPage
from .pages.dashboard import DashboardPage
from .pages.diagnostics import DiagnosticsPage
from .pages.history import HistoryPage
from .pages.memory import MemoryPage
from .pages.network import NetworkPage
from .pages.processes import ProcessesPage
from .pages.storage import StoragePage
from .theme import COLORS, font

log = logging.getLogger("systuklas.app")

NAV = [
    ("dashboard", "Dashboard", "dashboard", DashboardPage),
    ("cpu", "CPU", "cpu", CPUPage),
    ("memory", "Memory", "memory", MemoryPage),
    ("processes", "Processes", "process", ProcessesPage),
    ("storage", "Storage", "storage", StoragePage),
    ("network", "Network", "network", NetworkPage),
    ("diagnostics", "Diagnostics", "diagnostics", DiagnosticsPage),
    ("history", "History", "history", HistoryPage),
]
FULL_WIDTH, COMPACT_WIDTH, COMPACT_BREAKPOINT = 216, 70, 1000


class SysTuklasApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=COLORS["bg"])
        self.title("SysTuklas — Computer Performance Diagnostics")

        # ---- services (all sampling happens on background threads) ----
        self.db = Database()
        self.engine = DiagnosticEngine()
        self.monitor = SystemMonitor()
        self.procs = ProcessSampler()
        self.hw = HardwareInfo()
        self.recorder = HistoryRecorder(self.db)
        self.monitor.add_listener(self.recorder.on_sample)
        self.last_report = self.db.latest_report()
        self.monitor.start()
        self.procs.start()
        self.hw.probe_async()
        threading.Thread(target=lambda: self.db.purge_older_than(30), daemon=True).start()

        # ---- window size adapts to the screen ----
        try:
            scale = self._get_window_scaling()
        except Exception:
            scale = 1.0
        w = int(min(1320, self.winfo_screenwidth() / scale * 0.88))
        h = int(min(820, self.winfo_screenheight() / scale * 0.86))
        self.geometry(f"{w}x{h}")
        self.minsize(820, 540)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._compact = False
        self.pages: dict = {}
        self.current: str | None = None
        self._build_sidebar()
        self.main = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")

        self.report_callback_exception = lambda *a: log.error("UI callback error", exc_info=a)
        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._set_icon)
        self.show_page("dashboard")
        self.after(1000, self._tick)

    # ------------------------------------------------------------------ UI
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=FULL_WIDTH, corner_radius=0, fg_color=COLORS["sidebar"])
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(len(NAV) + 2, weight=1)
        self.sidebar = sb

        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=14, pady=(20, 18))
        ctk.CTkLabel(logo, text="", image=ctk_icon("logo", 30, COLORS["accent"])).pack(side="left")
        self.brand = ctk.CTkLabel(logo, text=" SysTuklas", font=font(19, "bold"))
        self.brand.pack(side="left")

        self.nav_buttons: dict = {}
        self._nav_icons: dict = {}
        for i, (key, label, icon, _cls) in enumerate(NAV, start=1):
            idle, active = ctk_icon(icon, 20, COLORS["muted"]), ctk_icon(icon, 20, COLORS["accent"])
            self._nav_icons[key] = (idle, active)
            b = ctk.CTkButton(sb, text="  " + label, image=idle, anchor="w", compound="left", height=42,
                              corner_radius=10, fg_color="transparent", hover_color=COLORS["card_alt"],
                              text_color=COLORS["muted"], font=font(14), command=lambda k=key: self.show_page(k))
            b.grid(row=i, column=0, sticky="ew", padx=10, pady=2)
            self.nav_buttons[key] = b
        sb.grid_columnconfigure(0, weight=1)

        foot = ctk.CTkFrame(sb, fg_color="transparent")
        foot.grid(row=len(NAV) + 3, column=0, sticky="ew", padx=14, pady=16)
        self.dot = ctk.CTkLabel(foot, text="● Live", font=font(12, "bold"), text_color=COLORS["good"], anchor="w")
        self.dot.pack(fill="x")
        self.foot_text = ctk.CTkLabel(foot, text="", font=font(11), text_color=COLORS["muted"], anchor="w")
        self.foot_text.pack(fill="x")

    def _on_resize(self, event):
        if event.widget is not self:
            return
        try:
            scale = self._get_window_scaling()
        except Exception:
            scale = 1.0
        compact = event.width / scale < COMPACT_BREAKPOINT
        if compact == self._compact:
            return
        self._compact = compact
        self.sidebar.configure(width=COMPACT_WIDTH if compact else FULL_WIDTH)
        for key, label, _icon, _cls in NAV:
            self.nav_buttons[key].configure(text="" if compact else "  " + label,
                                            anchor="center" if compact else "w")
        if compact:
            self.brand.pack_forget()
            self.foot_text.pack_forget()
            self.dot.configure(text="●")
        else:
            self.brand.pack(side="left")
            self.foot_text.pack(fill="x")
            self.dot.configure(text="● Live")

    def _set_icon(self):
        try:
            from PIL import ImageTk
            self._icon_img = ImageTk.PhotoImage(pil_icon("logo", 64, COLORS["accent"]))
            self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    # ---------------------------------------------------------- navigation
    def _get_page(self, key: str):
        if key not in self.pages:
            cls = next(c for k, _l, _i, c in NAV if k == key)
            self.pages[key] = cls(self.main, self)
        return self.pages[key]

    def show_page(self, key: str, run: bool = False):
        if self.current == key and not run:
            return
        if self.current and self.current != key:
            old = self.pages.get(self.current)
            if old:
                old.pack_forget()
                old.on_hide()
        page = self._get_page(key)
        page.pack(fill="both", expand=True)
        self.current = key
        for k, b in self.nav_buttons.items():
            on = k == key
            b.configure(fg_color=COLORS["card_alt"] if on else "transparent",
                        text_color=COLORS["text"] if on else COLORS["muted"],
                        image=self._nav_icons[k][1 if on else 0])
        page.on_show()
        page.refresh()
        if run and hasattr(page, "run_scan"):
            page.run_scan()

    # ---------------------------------------------------------------- loop
    def _tick(self):
        try:
            page = self.pages.get(self.current)
            if page:
                page.refresh()
            s = self.monitor.latest
            if s:
                rec = "recording" if self.recorder.enabled else "paused"
                text = f"CPU {s.cpu:.0f}% • RAM {s.ram_percent:.0f}%\nHistory {rec}"
                if getattr(self, "_foot_last", None) != text and not self._compact:
                    self._foot_last = text
                    self.foot_text.configure(text=text)
        except Exception:
            log.exception("refresh failed")
        self.after(1000, self._tick)

    def _on_close(self):
        try:
            self.recorder.flush()
        except Exception:
            pass
        self.monitor.stop()
        self.procs.stop()
        self.destroy()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    app = SysTuklasApp()
    app.mainloop()
