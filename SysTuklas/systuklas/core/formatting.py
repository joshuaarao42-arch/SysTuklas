"""Human-friendly formatting helpers (no UI or psutil dependency)."""
from __future__ import annotations

import time


def fmt_bytes(n, decimals: int = 1) -> str:
    if n is None:
        return "N/A"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            if unit == "B":
                return f"{n:.0f} B"
            return f"{n:.{decimals}f} {unit}"
        n /= 1024
    return f"{n:.{decimals}f} PB"


def fmt_rate(bps) -> str:
    return fmt_bytes(bps) + "/s"


def fmt_duration(seconds) -> str:
    if seconds is None:
        return "N/A"
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def fmt_freq(mhz) -> str:
    if mhz is None or mhz <= 0:
        return "N/A"
    return f"{mhz / 1000:.2f} GHz" if mhz >= 1000 else f"{mhz:.0f} MHz"


def fmt_time(ts, with_date: bool = True) -> str:
    if not ts:
        return "N/A"
    fmt = "%Y-%m-%d %H:%M:%S" if with_date else "%H:%M:%S"
    return time.strftime(fmt, time.localtime(ts))
