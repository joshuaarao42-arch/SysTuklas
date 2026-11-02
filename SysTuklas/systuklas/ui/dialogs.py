"""Modal dialogs: confirm, message, text viewer, report export."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ..core.exporter import export_report, report_to_text
from .theme import COLORS, font


class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=COLORS["bg"])
        self.resizable(False, False)
        self.result = None
        self._parent = parent.winfo_toplevel()
        self.transient(self._parent)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())

    def present(self):
        """Center over the parent, then make the dialog modal."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        p = self._parent
        x = p.winfo_rootx() + max(0, (p.winfo_width() - w) // 2)
        y = p.winfo_rooty() + max(0, (p.winfo_height() - h) // 3)
        tk.Toplevel.geometry(self, f"+{x}+{y}")
        self.after(30, self.lift)
        self.after(150, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def close(self, result=None):
        self.result = result
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def ask_confirm(parent, title: str, message: str, confirm_text: str = "Confirm", danger: bool = False,
                cancel_text: str = "Cancel") -> bool:
    dlg = BaseDialog(parent, title)
    box = ctk.CTkFrame(dlg, fg_color=COLORS["card"], corner_radius=14)
    box.pack(fill="both", expand=True, padx=14, pady=14)
    ctk.CTkLabel(box, text=title, font=font(17, "bold"), anchor="w").pack(fill="x", padx=20, pady=(18, 4))
    ctk.CTkLabel(box, text=message, font=font(13), text_color=COLORS["text"], justify="left", anchor="w",
                 wraplength=400).pack(fill="x", padx=20, pady=(4, 16))
    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=(0, 18))
    ctk.CTkButton(row, text=cancel_text, width=110, fg_color=COLORS["card_alt"], hover_color=COLORS["border"],
                  command=lambda: dlg.close(False)).pack(side="right", padx=(8, 0))
    ctk.CTkButton(row, text=confirm_text, width=130, fg_color=COLORS["bad"] if danger else COLORS["accent"],
                  hover_color="#DC2626" if danger else COLORS["accent_dark"], text_color="#0B0F14",
                  command=lambda: dlg.close(True)).pack(side="right")
    dlg.present()
    parent.wait_window(dlg)
    return bool(dlg.result)


def show_message(parent, title: str, message: str, kind: str = "info") -> None:
    color = {"info": COLORS["accent"], "error": COLORS["bad"], "warn": COLORS["warn"], "ok": COLORS["good"]}[kind]
    dlg = BaseDialog(parent, title)
    box = ctk.CTkFrame(dlg, fg_color=COLORS["card"], corner_radius=14)
    box.pack(fill="both", expand=True, padx=14, pady=14)
    ctk.CTkLabel(box, text=title, font=font(17, "bold"), text_color=color, anchor="w").pack(fill="x", padx=20, pady=(18, 4))
    ctk.CTkLabel(box, text=message, font=font(13), justify="left", anchor="w", wraplength=400).pack(
        fill="x", padx=20, pady=(4, 16))
    ctk.CTkButton(box, text="OK", width=100, command=dlg.close).pack(anchor="e", padx=20, pady=(0, 18))
    dlg.present()
    parent.wait_window(dlg)


def show_text(parent, title: str, text: str, width: int = 720, height: int = 520) -> None:
    dlg = BaseDialog(parent, title)
    dlg.resizable(True, True)
    box = ctk.CTkFrame(dlg, fg_color=COLORS["card"], corner_radius=14)
    box.pack(fill="both", expand=True, padx=14, pady=14)
    tb = ctk.CTkTextbox(box, width=width, height=height, font=ctk.CTkFont(family="Consolas", size=12),
                        fg_color=COLORS["bg"], wrap="word")
    tb.pack(fill="both", expand=True, padx=14, pady=(14, 8))
    tb.insert("1.0", text)
    tb.configure(state="disabled")
    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack(fill="x", padx=14, pady=(0, 14))

    def copy():
        dlg.clipboard_clear()
        dlg.clipboard_append(text)

    ctk.CTkButton(row, text="Close", width=100, command=dlg.close).pack(side="right")
    ctk.CTkButton(row, text="Copy", width=100, fg_color=COLORS["card_alt"], hover_color=COLORS["border"],
                  command=copy).pack(side="right", padx=8)
    dlg.present()
    parent.wait_window(dlg)


def export_report_dialog(parent, report) -> None:
    path = filedialog.asksaveasfilename(
        parent=parent.winfo_toplevel(), title="Export diagnostic report", defaultextension=".html",
        initialfile="SysTuklas-report",
        filetypes=[("HTML report", "*.html"), ("Text report", "*.txt"), ("JSON data", "*.json")])
    if not path:
        return
    try:
        export_report(report, path)
        show_message(parent, "Report exported", f"Saved to:\n{path}", "ok")
    except OSError as exc:
        show_message(parent, "Export failed", f"Could not write the file:\n{exc}", "error")


def view_report_dialog(parent, report) -> None:
    show_text(parent, "Diagnostic report", report_to_text(report))
