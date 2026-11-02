"""Reusable themed widgets: cards, stat cards, charts, tables."""
from __future__ import annotations

import math
from datetime import datetime
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.dates as mdates  # noqa: E402
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from .theme import COLORS, FONT_FAMILY, font, usage_color  # noqa: E402


def cfg(widget, **kw) -> None:
    """widget.configure(**kw), but only if a value actually changed.

    CustomTkinter redraws a widget on every configure() call, which is expensive
    when dozens of labels are refreshed every second."""
    cache = widget.__dict__.setdefault("_cfg_cache", {})
    changed = {k: v for k, v in kw.items() if cache.get(k, object()) != v}
    if changed:
        cache.update(changed)
        widget.configure(**changed)


# --------------------------------------------------------------------------- #
# containers
# --------------------------------------------------------------------------- #
class Card(ctk.CTkFrame):
    """Rounded card. Put content in ``card.body``."""

    def __init__(self, master, title: str | None = None, **kw):
        kw.setdefault("fg_color", COLORS["card"])
        kw.setdefault("corner_radius", 8)
        kw.setdefault("border_width", 0)
        super().__init__(master, **kw)
        self.title_label = None
        if title:
            self.title_label = ctk.CTkLabel(self, text=title, font=font(13, "bold"),
                                            text_color=COLORS["muted"], anchor="w")
            self.title_label.pack(fill="x", padx=16, pady=(12, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        # small inset so the transparent body never paints over the card's rounded border
        self.body.pack(fill="both", expand=True, padx=2, pady=(0, 2))


class ReflowFrame(ctk.CTkFrame):
    """Lays children out in as many equal columns as fit (responsive grid)."""

    def __init__(self, master, min_width: int = 240, gap: int = 10, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        self.min_width, self.gap = min_width, gap
        self._items: list = []
        self._cols = 0
        self._max_cols = 0
        self._pending = None
        self.bind("<Configure>", self._schedule)

    def _schedule(self, _e=None) -> None:
        """Re-flow only after resizing pauses (avoids re-laying out on every pixel)."""
        if self._pending is not None:
            self.after_cancel(self._pending)
        self._pending = self.after(120, self._run_layout)

    def _run_layout(self) -> None:
        self._pending = None
        self._layout()

    def add(self, widget) -> None:
        self._items.append(widget)
        self._layout(force=True)

    def _layout(self, force: bool = False) -> None:
        if not self._items:
            return
        width = self.winfo_width()
        if width <= 1:
            width = self.min_width * 2
        scale = 1.0
        try:
            scale = self._get_widget_scaling()
        except Exception:
            pass
        width = width / scale
        cols = max(1, min(len(self._items), int((width + self.gap) // (self.min_width + self.gap))))
        if cols == self._cols and not force:
            return
        self._cols = cols
        self._max_cols = max(self._max_cols, cols)
        for c in range(self._max_cols):
            self.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="reflow" if c < cols else "")
        half = self.gap // 2
        for i, w in enumerate(self._items):
            w.grid(row=i // cols, column=i % cols, sticky="nsew", padx=half, pady=half)


class ScrollFrame(tk.Frame):
    """Fast vertical scroll container (plain Tk canvas; much lighter than CTkScrollableFrame).
    Put content in ``.inner``."""

    def __init__(self, master):
        super().__init__(master, bg=COLORS["bg"], highlightthickness=0, bd=0)
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0, bd=0, yscrollincrement=30)
        self.vsb = ctk.CTkScrollbar(self, command=self.canvas.yview, width=12)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ctk.CTkFrame(self.canvas, fg_color="transparent", corner_radius=0)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self._region_job = None
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.inner.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))

    def _on_inner(self, _e=None):
        if self._region_job is None:
            self._region_job = self.after(60, self._update_region)

    def _update_region(self):
        self._region_job = None
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _wheel(self, e):
        bbox = self.canvas.bbox("all")
        if bbox and (bbox[3] - bbox[1]) > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120) * 2, "units")


class KeyValueCard(Card):
    def __init__(self, master, title: str, keys: list):
        super().__init__(master, title)
        self.body.grid_columnconfigure(1, weight=1)
        self._vals: dict = {}
        for i, key in enumerate(keys):
            ctk.CTkLabel(self.body, text=key, font=font(12), text_color=COLORS["muted"], anchor="w").grid(
                row=i, column=0, sticky="nw", padx=(16, 8), pady=3)
            lbl = ctk.CTkLabel(self.body, text="—", font=font(12), anchor="w", justify="left")
            lbl.grid(row=i, column=1, sticky="nw", padx=(0, 12), pady=3)
            self._vals[key] = lbl
        ctk.CTkFrame(self.body, height=8, fg_color="transparent").grid(row=len(keys), column=0)
        self.bind("<Configure>", self._wrap, add="+")

    def _wrap(self, e):
        try:
            sc = self._get_widget_scaling()
        except Exception:
            sc = 1.0
        w = max(120, int((e.width - 150) / sc))
        for lbl in self._vals.values():
            if abs(getattr(lbl, "_ww", 0) - w) > 8:
                lbl._ww = w
                lbl.configure(wraplength=w)

    def set(self, key: str, value) -> None:
        lbl = self._vals.get(key)
        if lbl is not None:
            cfg(lbl, text=str(value))


class RankList(Card):
    """Small 'top N' list: name on the left, value on the right."""

    def __init__(self, master, title: str, rows: int = 5):
        super().__init__(master, title)
        self.body.grid_columnconfigure(0, weight=1)
        self._rows = []
        for i in range(rows):
            n = ctk.CTkLabel(self.body, text="", font=font(12), anchor="w")
            v = ctk.CTkLabel(self.body, text="", font=font(12, "bold"), anchor="e", text_color=COLORS["accent"])
            n.grid(row=i, column=0, sticky="ew", padx=(16, 4), pady=3)
            v.grid(row=i, column=1, sticky="e", padx=(4, 16), pady=3)
            self._rows.append((n, v))
        ctk.CTkFrame(self.body, height=8, fg_color="transparent").grid(row=rows, column=0)

    def update_rows(self, rows: list) -> None:
        for i, (n, v) in enumerate(self._rows):
            name, val = rows[i] if i < len(rows) else ("", "")
            if len(name) > 28:
                name = name[:27] + "…"
            cfg(n, text=name)
            cfg(v, text=val)


class StatCard(Card):
    def __init__(self, master, title: str, accent: str | None = None, show_bar: bool = True):
        super().__init__(master, title)
        self.accent = accent or COLORS["accent"]
        self.value = ctk.CTkLabel(self.body, text="--", font=font(26, "bold"), anchor="w")
        self.value.pack(fill="x", padx=16, pady=(2, 0))
        self.sub = ctk.CTkLabel(self.body, text=" ", font=font(12), text_color=COLORS["muted"], anchor="w")
        self.sub.pack(fill="x", padx=16)
        self.bar = None
        if show_bar:
            self.bar = ctk.CTkProgressBar(self.body, height=6, corner_radius=3, progress_color=self.accent,
                                          fg_color=COLORS["card_alt"])
            self.bar.set(0)
            self.bar.pack(fill="x", padx=16, pady=(8, 14))
        else:
            ctk.CTkFrame(self.body, height=12, fg_color="transparent").pack()
        self.sub.bind("<Configure>", lambda e: None)

    def update_values(self, value: str, sub: str = " ", percent: float | None = None, color: str | None = None):
        cfg(self.value, text=value)
        cfg(self.sub, text=sub or " ")
        if self.bar is not None and percent is not None:
            step = round(max(0.0, min(100.0, percent)))  # 1 % resolution is plenty for a bar
            if getattr(self, "_bar_step", None) != step:
                self._bar_step = step
                self.bar.set(step / 100.0)
            cfg(self.bar, progress_color=color or self.accent)


class StatusBadge(ctk.CTkLabel):
    def __init__(self, master, text: str, color: str):
        super().__init__(master, text=f"  {text}  ", fg_color=color, text_color="#0B0F14", corner_radius=8,
                         font=font(11, "bold"))

    def set(self, text: str, color: str):
        cfg(self, text=f"  {text}  ", fg_color=color)


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def _style_axes(ax, fig):
    ax.set_facecolor(COLORS["card"])
    fig.set_facecolor(COLORS["card"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLORS["border"])
    ax.tick_params(colors=COLORS["muted"], labelsize=8, length=3)
    ax.grid(True, color=COLORS["border"], alpha=0.6, linewidth=0.6)
    ax.yaxis.label.set_color(COLORS["muted"])


class LiveChart(ctk.CTkFrame):
    """Rolling line chart (x axis = seconds ago)."""

    def __init__(self, master, series: list, window: int = 120, height: int = 220, fill: bool = False,
                 min_top: float = 1.0, ylabel: str = ""):
        super().__init__(master, fg_color="transparent", height=height)
        self.window, self.fill, self.min_top = window, fill, min_top
        self.fig = Figure(figsize=(6, 2.4), dpi=100)
        self.fig.subplots_adjust(left=0.085, right=0.965, top=0.92, bottom=0.17)  # cheap, fixed layout
        self.ax = self.fig.add_subplot(111)
        _style_axes(self.ax, self.fig)
        self.ax.set_xlim(-window, 0)
        ticks = list(range(-window, 1, 30)) if window >= 60 else [-window, 0]
        self.ax.set_xticks(ticks)
        self.ax.set_xticklabels(["now" if t == 0 else f"-{abs(t)}s" for t in ticks])
        if ylabel:
            self.ax.set_ylabel(ylabel, fontsize=8)
        self.lines, self.colors, self._fills = {}, {}, []
        for key, label, color in series:
            (line,) = self.ax.plot([], [], color=color, lw=1.8, label=label)
            self.lines[key], self.colors[key] = line, color
        if len(series) > 1:
            self.ax.legend(loc="upper left", frameon=False, labelcolor=COLORS["muted"], fontsize=8, ncol=len(series))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        widget = self.canvas.get_tk_widget()
        widget.configure(bg=COLORS["card"], highlightthickness=0)
        widget.pack(fill="both", expand=True)

    def update_data(self, data: dict, ymax: float | None = None, ylabel: str | None = None):
        n = min(self.window, max((len(v) for v in data.values()), default=0))
        if n == 0:
            return
        self._calls = getattr(self, "_calls", 0) + 1
        if self._calls % 2 == 0:  # redraw every 2 s: halves the most expensive work in the app
            return
        xs = list(range(-n + 1, 1))
        peak = 0.0
        for key, line in self.lines.items():
            ys = [float(y) if y is not None else math.nan for y in list(data.get(key, []))[-n:]]
            if len(ys) < n:
                ys = [math.nan] * (n - len(ys)) + ys
            line.set_data(xs, ys)
            peak = max(peak, max((y for y in ys if y == y), default=0.0))
        for f in self._fills:
            try:
                f.remove()
            except Exception:
                pass
        self._fills = []
        if self.fill:
            for key, line in self.lines.items():
                self._fills.append(self.ax.fill_between(xs, line.get_ydata(), color=self.colors[key],
                                                        alpha=0.10, linewidth=0))
        self.ax.set_ylim(0, ymax if ymax is not None else max(peak * 1.25, self.min_top))
        if ylabel is not None:
            self.ax.set_ylabel(ylabel, fontsize=8)
        self.canvas.draw_idle()


class HistoryChart(ctk.CTkFrame):
    """Time-series chart for stored history, with gap handling."""

    def __init__(self, master, height: int = 300):
        super().__init__(master, fg_color="transparent", height=height)
        self.fig = Figure(figsize=(6, 3), dpi=100, layout="constrained")
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        w = self.canvas.get_tk_widget()
        w.configure(bg=COLORS["card"], highlightthickness=0)
        w.pack(fill="both", expand=True)
        self.show_message("Loading…")

    def show_message(self, text: str):
        self.ax.clear()
        _style_axes(self.ax, self.fig)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.text(0.5, 0.5, text, transform=self.ax.transAxes, ha="center", va="center",
                     color=COLORS["muted"], fontsize=10)
        self.canvas.draw_idle()

    def plot(self, times: list, series: list, ylabel: str = "", ymax: float | None = None):
        """series: list of dicts {label, color, values}."""
        if not times:
            self.show_message("No data recorded for this period yet.\nKeep SysTuklas running to build history.")
            return
        self.ax.clear()
        _style_axes(self.ax, self.fig)
        gaps = []
        if len(times) > 2:
            diffs = sorted(b - a for a, b in zip(times, times[1:]))
            med = diffs[len(diffs) // 2]
            limit = max(med * 4, 60)
            gaps = [i + 1 for i, (a, b) in enumerate(zip(times, times[1:])) if b - a > limit]
        xs = list(times)
        for g in reversed(gaps):
            xs.insert(g, xs[g - 1] + 1)
        dts = [datetime.fromtimestamp(t) for t in xs]
        peak = 0.0
        for s in series:
            ys = list(s["values"])
            for g in reversed(gaps):
                ys.insert(g, math.nan)
            ys = [math.nan if v is None else v for v in ys]
            peak = max(peak, max((v for v in ys if v == v), default=0.0))
            few = len(dts) <= 3
            self.ax.plot(dts, ys, color=s["color"], lw=1.6, label=s["label"],
                         marker="o" if few else None, ms=5)
            if not few:
                self.ax.fill_between(dts, ys, color=s["color"], alpha=0.07, linewidth=0)
        if len(dts) == 1:  # a single point has no extent: give the axis a sensible window
            from datetime import timedelta
            self.ax.set_xlim(dts[0] - timedelta(minutes=2), dts[0] + timedelta(minutes=2))
        loc = mdates.AutoDateLocator(minticks=3, maxticks=7)
        self.ax.xaxis.set_major_locator(loc)
        self.ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
        self.ax.set_ylim(0, ymax if ymax else max(peak * 1.25, 1.0))
        if ylabel:
            self.ax.set_ylabel(ylabel, fontsize=8)
        self.ax.legend(loc="upper left", frameon=False, labelcolor=COLORS["muted"], fontsize=8, ncol=len(series))
        self.canvas.draw_idle()

    def save_png(self, path: str) -> None:
        self.fig.savefig(path, dpi=150, facecolor=self.fig.get_facecolor())


# --------------------------------------------------------------------------- #
# table
# --------------------------------------------------------------------------- #
class DataTable(ctk.CTkFrame):
    """Sortable table that updates rows in place (keeps scroll and selection).

    columns: list of dicts {key, title, width, anchor, numeric}
    rows:    list of dicts {iid, values (display strings), sort (raw values)}
    """
    _style_ready = False

    def __init__(self, master, columns: list, height: int = 10, on_double=None, on_select=None):
        super().__init__(master, fg_color=COLORS["card"], corner_radius=10)
        self._setup_style()
        self.columns = columns
        self._rows: list = []
        self._sort_idx: int | None = None
        self._sort_desc = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(self, columns=[c["key"] for c in columns], show="headings",
                                 style="Sys.Treeview", selectmode="browse", height=height)
        sb = ctk.CTkScrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sb.grid(row=0, column=1, sticky="ns", padx=(2, 4), pady=6)
        for i, c in enumerate(columns):
            self.tree.heading(c["key"], text=c["title"], anchor=c.get("anchor", "w"),
                              command=lambda k=c["key"]: self._header_click(k))
            self.tree.column(c["key"], width=c.get("width", 100), anchor=c.get("anchor", "w"),
                             stretch=c.get("stretch", True), minwidth=50)
        if on_double:
            self.tree.bind("<Double-1>", lambda e: on_double())
        if on_select:
            self.tree.bind("<<TreeviewSelect>>", lambda e: on_select())

    @classmethod
    def _setup_style(cls):
        if cls._style_ready:
            return
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Sys.Treeview", background=COLORS["card"], fieldbackground=COLORS["card"],
                     foreground=COLORS["text"], borderwidth=0, rowheight=28, font=(FONT_FAMILY, 10),
                     bordercolor=COLORS["card"], lightcolor=COLORS["card"], darkcolor=COLORS["card"])
        st.map("Sys.Treeview", background=[("selected", COLORS["accent_dark"])], foreground=[("selected", "#FFFFFF")])
        st.configure("Sys.Treeview.Heading", background=COLORS["card_alt"], foreground=COLORS["muted"],
                     relief="flat", borderwidth=0, font=(FONT_FAMILY, 10, "bold"), padding=(6, 6),
                     bordercolor=COLORS["card_alt"], lightcolor=COLORS["card_alt"], darkcolor=COLORS["card_alt"])
        st.map("Sys.Treeview.Heading", background=[("active", COLORS["border"])])
        cls._style_ready = True

    # --- sorting ---
    def _col_index(self, key: str) -> int:
        return next(i for i, c in enumerate(self.columns) if c["key"] == key)

    def _header_click(self, key: str):
        idx = self._col_index(key)
        if self._sort_idx == idx:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_idx = idx
            self._sort_desc = bool(self.columns[idx].get("numeric"))
        self._render()

    def set_sort(self, key: str, desc: bool | None = None):
        idx = self._col_index(key)
        self._sort_idx = idx
        self._sort_desc = bool(self.columns[idx].get("numeric")) if desc is None else desc
        self._render()

    # --- data ---
    def set_rows(self, rows: list):
        self._rows = rows
        self._render()

    def selected(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def row_values(self, iid: str):
        return self.tree.item(iid, "values")

    def _render(self):
        rows = list(self._rows)
        if self._sort_idx is not None:
            i = self._sort_idx
            rows.sort(key=lambda r: r["sort"][i], reverse=self._sort_desc)
        for j, c in enumerate(self.columns):
            arrow = (" ▼" if self._sort_desc else " ▲") if j == self._sort_idx else ""
            self.tree.heading(c["key"], text=c["title"] + arrow)
        existing = set(self.tree.get_children())
        wanted = [r["iid"] for r in rows]
        for iid in existing - set(wanted):
            self.tree.delete(iid)
        for r in rows:
            if r["iid"] in existing:
                self.tree.item(r["iid"], values=r["values"])
            else:
                self.tree.insert("", "end", iid=r["iid"], values=r["values"])
        if list(self.tree.get_children()) != wanted:
            for i, iid in enumerate(wanted):
                self.tree.move(iid, "", i)
