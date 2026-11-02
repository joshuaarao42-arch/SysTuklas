"""Base class shared by every page."""
from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, font
from ..widgets import ScrollFrame


class BasePage(ctk.CTkFrame):
    def __init__(self, master, app, title: str, subtitle: str = "", scrollable: bool = False):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.monitor = app.monitor
        self.procs = app.procs
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(20, 8))
        head.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(head, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(left, text=title, font=font(24, "bold"), anchor="w").pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(left, text=subtitle, font=font(13), text_color=COLORS["muted"], anchor="w").pack(anchor="w")
        self.actions = ctk.CTkFrame(head, fg_color="transparent", width=1, height=1)
        self.actions.grid(row=0, column=1, sticky="e")
        if scrollable:
            sf = ScrollFrame(self)
            sf.pack(fill="both", expand=True, padx=(18, 10), pady=(0, 12))
            self.content = sf.inner
        else:
            self.content = ctk.CTkFrame(self, fg_color="transparent")
            self.content.pack(fill="both", expand=True, padx=24, pady=(0, 16))

    # lifecycle hooks -------------------------------------------------------
    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        pass

    def refresh(self) -> None:
        """Called about once per second while the page is visible."""
