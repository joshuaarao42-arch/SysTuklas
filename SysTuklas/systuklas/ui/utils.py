"""UI utilities: thread helper, auto-wrapping labels, unit selection."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Callable


def run_async(widget, func: Callable, callback: Callable, poll_ms: int = 60) -> None:
    """Run ``func`` on a worker thread; call ``callback(result, error)`` on the Tk thread.

    Tk is not thread-safe, so the worker only puts its result on a queue and the
    main thread polls the queue with ``after``.
    """
    q: queue.Queue = queue.Queue()

    def worker():
        try:
            q.put((func(), None))
        except Exception as exc:  # noqa: BLE001 - reported to the callback
            q.put((None, exc))

    threading.Thread(target=worker, daemon=True).start()

    def poll():
        try:
            res, err = q.get_nowait()
        except queue.Empty:
            try:
                widget.after(poll_ms, poll)
            except tk.TclError:
                pass
            return
        try:
            if widget.winfo_exists():
                callback(res, err)
        except tk.TclError:
            pass

    widget.after(poll_ms, poll)


def auto_wrap(label, container, pad: int = 48) -> None:
    """Keep ``label`` wrapped to the width of ``container`` (responsive text)."""
    state = {"w": 0}

    def on_cfg(event):
        try:
            scale = label._get_widget_scaling()
        except Exception:
            scale = 1.0
        w = max(160, int((event.width - pad) / scale))
        if abs(w - state["w"]) >= 8:
            state["w"] = w
            label.configure(wraplength=w)

    container.bind("<Configure>", on_cfg, add="+")


def choose_unit(max_bps: float):
    """Pick a display unit for a data rate: returns (divisor, label)."""
    if max_bps >= 1024 ** 2:
        return 1024 ** 2, "MB/s"
    if max_bps >= 1024:
        return 1024, "KB/s"
    return 1, "B/s"
