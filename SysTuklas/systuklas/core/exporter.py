"""Export diagnostic reports and performance history to files."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .formatting import fmt_bytes, fmt_duration, fmt_time
from .models import DiagnosticReport

SEV_TAG = {"critical": "CRITICAL", "warning": "WARNING", "info": "NOTICE", "ok": "HEALTHY"}
SEV_COLOR = {"critical": "#dc2626", "warning": "#d97706", "info": "#2563eb", "ok": "#059669"}


def _system_lines(system: dict) -> list:
    rows = [
        ("Computer", system.get("hostname")), ("Operating system", system.get("os")),
        ("Processor", system.get("cpu_name")),
        ("Cores / threads", f"{system.get('physical_cores')} / {system.get('logical_cores')}"),
        ("Memory", fmt_bytes(system.get("ram_total")) if system.get("ram_total") else None),
        ("Graphics", system.get("gpu")),
        ("Uptime", fmt_duration(system.get("uptime_seconds")) if system.get("uptime_seconds") else None),
    ]
    return [(k, str(v)) for k, v in rows if v]


def report_to_text(r: DiagnosticReport) -> str:
    line = "=" * 72
    out = [line, "SysTuklas - Diagnostic Report", line,
           f"Generated : {fmt_time(r.generated_at)}",
           f"Health    : {r.health_score}/100 ({r.health_label})",
           f"Data used : {r.metrics.get('samples', 0)} measurements over {fmt_duration(r.window_seconds)}",
           "", "SUMMARY", "-" * 72, r.summary, "", "FINDINGS", "-" * 72]
    for i, f in enumerate(r.findings, 1):
        out.append(f"{i}. [{SEV_TAG[f.severity]}] {f.category}: {f.title}")
        out.append(f"   {f.detail}")
        if f.recommendation:
            out.append(f"   Recommendation: {f.recommendation}")
        out.append("")
    out += ["MEASURED VALUES", "-" * 72]
    labels = {"cpu_avg": "CPU average (%)", "cpu_peak": "CPU peak (%)", "ram_avg": "Memory average (%)",
              "ram_peak": "Memory peak (%)", "swap_avg": "Page file average (%)", "ram_available": "Memory available",
              "system_drive_used": "System drive used (%)", "disk_io_avg": "Disk activity (avg)",
              "net_down_avg": "Download (avg)", "net_up_avg": "Upload (avg)", "processes": "Running processes",
              "samples": "Measurements", "window": "Measurement window"}
    for k, label in labels.items():
        if k in r.metrics:
            out.append(f"{label:<26}: {r.metrics[k]}")
    out += ["", "SYSTEM", "-" * 72]
    out += [f"{k:<26}: {v}" for k, v in _system_lines(r.system)]
    if r.notes:
        out += ["", "NOTES", "-" * 72] + [f"* {n}" for n in r.notes]
    return "\n".join(out) + "\n"


def report_to_html(r: DiagnosticReport) -> str:
    e = html.escape
    cards = []
    for f in r.findings:
        rec = f"<p class='rec'>&rarr; {e(f.recommendation)}</p>" if f.recommendation else ""
        cards.append(
            f"<div class='card' style='border-left:6px solid {SEV_COLOR[f.severity]}'>"
            f"<span class='tag' style='background:{SEV_COLOR[f.severity]}'>{SEV_TAG[f.severity]}</span> "
            f"<span class='cat'>{e(f.category)}</span><h3>{e(f.title)}</h3><p>{e(f.detail)}</p>{rec}</div>")
    sys_rows = "".join(f"<tr><td>{e(k)}</td><td>{e(v)}</td></tr>" for k, v in _system_lines(r.system))
    met_rows = "".join(f"<tr><td>{e(str(k))}</td><td>{e(str(v))}</td></tr>" for k, v in r.metrics.items())
    notes = "".join(f"<li>{e(n)}</li>" for n in r.notes)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SysTuklas Report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:30px auto;color:#1f2937;padding:0 16px}}
h1{{margin-bottom:0}}.score{{font-size:42px;font-weight:700}}.card{{background:#f9fafb;border:1px solid #e5e7eb;
border-radius:10px;padding:10px 16px;margin:12px 0}}.tag{{color:#fff;font-size:11px;padding:2px 8px;border-radius:6px;font-weight:700}}
.cat{{color:#6b7280;font-size:12px}}.rec{{color:#1d4ed8}}table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #e5e7eb;padding:6px 8px}}
td:first-child{{color:#6b7280;width:40%}}</style></head><body>
<h1>SysTuklas Diagnostic Report</h1><p>Generated {e(fmt_time(r.generated_at))}</p>
<div class="score">{r.health_score}/100 <small>{e(r.health_label)}</small></div><p>{e(r.summary)}</p>
<h2>Findings</h2>{''.join(cards)}<h2>Measured values</h2><table>{met_rows}</table>
<h2>System</h2><table>{sys_rows}</table><h2>Notes</h2><ul>{notes}</ul></body></html>"""


def export_report(report: DiagnosticReport, path: str) -> None:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".json":
        text = json.dumps(report.to_dict(), indent=2)
    elif ext in (".html", ".htm"):
        text = report_to_html(report)
    else:
        text = report_to_text(report)
    p.write_text(text, encoding="utf-8")


def export_history_csv(rows: list, path: str) -> int:
    cols = ["ts", "time", "cpu", "cpu_max", "ram", "swap", "disk", "disk_read", "disk_write", "net_up", "net_down"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "local_time", "cpu_avg_pct", "cpu_peak_pct", "ram_pct", "swap_pct", "disk_pct",
                    "disk_read_Bps", "disk_write_Bps", "net_up_Bps", "net_down_Bps"])
        for r in rows:
            w.writerow([r.get("ts"), fmt_time(r.get("ts"))] + [round(r.get(c) or 0, 2) for c in cols[2:]])
    return len(rows)
