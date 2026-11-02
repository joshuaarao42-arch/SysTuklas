"""Plain data models shared by the monitoring, diagnostic and UI layers."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Snapshot:
    """One measurement of the whole system (taken about once per second)."""
    ts: float
    cpu: float
    per_core: list
    freq_current: Optional[float]
    freq_max: Optional[float]
    ram_percent: float
    ram_total: int
    ram_used: int
    ram_available: int
    swap_percent: float
    swap_total: int
    swap_used: int
    disk_percent: float
    disk_free: int
    disk_total: int
    disk_read_bps: float
    disk_write_bps: float
    net_up_bps: float
    net_down_bps: float
    net_sent_total: int
    net_recv_total: int
    temperature: Optional[float] = None
    battery_percent: Optional[float] = None
    battery_plugged: Optional[bool] = None


@dataclass
class Finding:
    severity: str          # critical | warning | info | ok
    category: str
    title: str
    detail: str
    recommendation: str = ""


@dataclass
class DiagnosticReport:
    generated_at: float
    health_score: int
    health_label: str
    summary: str
    findings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    window_seconds: float = 0.0

    @property
    def counts(self) -> dict:
        out = {"critical": 0, "warning": 0, "info": 0, "ok": 0}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DiagnosticReport":
        findings = [Finding(**f) for f in d.get("findings", [])]
        return cls(
            generated_at=d.get("generated_at", 0.0),
            health_score=int(d.get("health_score", 0)),
            health_label=d.get("health_label", ""),
            summary=d.get("summary", ""),
            findings=findings,
            metrics=d.get("metrics", {}),
            system=d.get("system", {}),
            notes=d.get("notes", []),
            window_seconds=d.get("window_seconds", 0.0),
        )


def aggregate_apps(processes: list) -> list:
    """Group process rows by executable name (e.g. all chrome.exe together)."""
    apps: dict = {}
    for p in processes:
        name = p.get("name") or "?"
        key = name.lower()
        a = apps.get(key)
        if a is None:
            a = apps[key] = {"name": name, "count": 0, "cpu": 0.0, "rss": 0}
        a["count"] += 1
        a["cpu"] += p.get("cpu") or 0.0
        a["rss"] += p.get("rss") or 0
    return list(apps.values())
