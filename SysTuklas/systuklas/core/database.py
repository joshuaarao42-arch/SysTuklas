"""SQLite persistence: performance samples, saved diagnostic reports, settings."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from .models import DiagnosticReport, Snapshot

log = logging.getLogger("systuklas.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    cpu REAL, cpu_max REAL, ram REAL, swap REAL, disk REAL,
    disk_read REAL, disk_write REAL, net_up REAL, net_down REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    score INTEGER, label TEXT, summary TEXT,
    critical INTEGER, warning INTEGER,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


def default_db_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "SysTuklas" / "systuklas.db"


class Database:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            try:
                c.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        with self._lock:
            conn = sqlite3.connect(str(self.path), timeout=15)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # ----- samples -----
    def insert_sample(self, row: dict) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO samples (ts,cpu,cpu_max,ram,swap,disk,disk_read,disk_write,net_up,net_down) "
                "VALUES (:ts,:cpu,:cpu_max,:ram,:swap,:disk,:disk_read,:disk_write,:net_up,:net_down)", row)

    def query_series(self, since: float, until: Optional[float] = None, max_points: int = 600) -> list:
        until = until or time.time()
        bucket = max(10.0, (until - since) / max_points)
        with self._conn() as c:
            cur = c.execute(
                "SELECT AVG(ts) AS ts, AVG(cpu) AS cpu, MAX(cpu_max) AS cpu_max, AVG(ram) AS ram, "
                "AVG(swap) AS swap, AVG(disk) AS disk, AVG(disk_read) AS disk_read, "
                "AVG(disk_write) AS disk_write, AVG(net_up) AS net_up, AVG(net_down) AS net_down "
                "FROM samples WHERE ts BETWEEN :a AND :b "
                "GROUP BY CAST(ts / :k AS INTEGER) ORDER BY ts",
                {"a": since, "b": until, "k": bucket})
            return [dict(r) for r in cur.fetchall()]

    def raw_samples(self, since: float) -> list:
        with self._conn() as c:
            cur = c.execute("SELECT * FROM samples WHERE ts >= ? ORDER BY ts", (since,))
            return [dict(r) for r in cur.fetchall()]

    def summary(self, since: float) -> dict:
        with self._conn() as c:
            r = c.execute(
                "SELECT COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts, "
                "AVG(cpu) AS cpu_avg, MAX(cpu_max) AS cpu_peak, AVG(ram) AS ram_avg, MAX(ram) AS ram_peak, "
                "AVG(disk) AS disk_avg, MAX(disk) AS disk_peak, AVG(net_down) AS down_avg, AVG(net_up) AS up_avg "
                "FROM samples WHERE ts >= ?", (since,)).fetchone()
        d = dict(r)
        d["n"] = d["n"] or 0
        span = ((d["last_ts"] or 0) - (d["first_ts"] or 0)) if d["n"] else 0
        d["span_seconds"] = span
        d["hours"] = span / 3600.0
        return d

    def purge_older_than(self, days: int = 30) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM samples WHERE ts < ?", (time.time() - days * 86400,))

    def clear_history(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM samples")
        with self._conn() as c:
            c.execute("VACUUM")

    # ----- reports -----
    def save_report(self, report: DiagnosticReport) -> int:
        counts = report.counts
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO reports (ts,score,label,summary,critical,warning,body) VALUES (?,?,?,?,?,?,?)",
                (report.generated_at, report.health_score, report.health_label, report.summary,
                 counts["critical"], counts["warning"], json.dumps(report.to_dict())))
            return cur.lastrowid

    def list_reports(self, limit: int = 200) -> list:
        with self._conn() as c:
            cur = c.execute(
                "SELECT id,ts,score,label,summary,critical,warning FROM reports ORDER BY ts DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_report(self, report_id: int) -> Optional[DiagnosticReport]:
        with self._conn() as c:
            r = c.execute("SELECT body FROM reports WHERE id=?", (report_id,)).fetchone()
        return DiagnosticReport.from_dict(json.loads(r["body"])) if r else None

    def latest_report(self) -> Optional[DiagnosticReport]:
        with self._conn() as c:
            r = c.execute("SELECT body FROM reports ORDER BY ts DESC LIMIT 1").fetchone()
        try:
            return DiagnosticReport.from_dict(json.loads(r["body"])) if r else None
        except Exception:
            return None

    def delete_report(self, report_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM reports WHERE id=?", (report_id,))

    # ----- settings -----
    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as c:
            r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


class HistoryRecorder:
    """Averages live samples into one database row every ``interval`` seconds."""

    def __init__(self, db: Database, interval: float = 10.0):
        self.db = db
        self.interval = interval
        self.enabled = db.get_setting("recording", "1") == "1"
        self._buf: list = []
        self._start: Optional[float] = None
        self._lock = threading.Lock()

    def set_enabled(self, flag: bool) -> None:
        self.enabled = flag
        self.db.set_setting("recording", "1" if flag else "0")
        if not flag:
            self.flush()

    def on_sample(self, s: Snapshot) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._start is None:
                self._start = s.ts
            self._buf.append(s)
            if s.ts - self._start >= self.interval:
                self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        buf, self._buf, self._start = self._buf, [], None
        if not buf:
            return
        n = len(buf)

        def avg(attr):
            return sum(getattr(s, attr) for s in buf) / n

        try:
            self.db.insert_sample({
                "ts": buf[-1].ts, "cpu": avg("cpu"), "cpu_max": max(s.cpu for s in buf),
                "ram": avg("ram_percent"), "swap": avg("swap_percent"), "disk": avg("disk_percent"),
                "disk_read": avg("disk_read_bps"), "disk_write": avg("disk_write_bps"),
                "net_up": avg("net_up_bps"), "net_down": avg("net_down_bps"),
            })
        except Exception:
            log.exception("could not save sample")
