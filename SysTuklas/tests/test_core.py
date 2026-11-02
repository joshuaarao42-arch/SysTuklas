import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from systuklas.core.database import Database, HistoryRecorder
from systuklas.core.diagnostics import DiagnosticEngine
from systuklas.core.exporter import report_to_html, report_to_text, export_report
from systuklas.core.models import Snapshot


def snap(i, cpu=20.0, ram=40.0, **kw):
    base = dict(ts=1000.0 + i, cpu=cpu, per_core=[cpu], freq_current=3000, freq_max=4000, ram_percent=ram,
                ram_total=16 * 1024**3, ram_used=int(16 * 1024**3 * ram / 100),
                ram_available=int(16 * 1024**3 * (100 - ram) / 100), swap_percent=5, swap_total=1, swap_used=0,
                disk_percent=50, disk_free=100 * 1024**3, disk_total=200 * 1024**3, disk_read_bps=0, disk_write_bps=0,
                net_up_bps=0, net_down_bps=0, net_sent_total=0, net_recv_total=0)
    base.update(kw)
    return Snapshot(**base)


def disks(free_pct=50):
    t = 500 * 1024**3
    return [{"device": "C:", "mountpoint": "C:\\", "fstype": "NTFS", "total": t, "used": t * (100 - free_pct) // 100,
             "free": t * free_pct // 100, "percent": 100 - free_pct}]


def test_normal_system_is_healthy():
    r = DiagnosticEngine().analyze([snap(i) for i in range(60)], [], disks(), {})
    assert r.health_score == 100 and r.counts["critical"] == 0 and r.counts["warning"] == 0


def test_spike_is_not_a_problem():
    s = [snap(i, cpu=15) for i in range(60)]
    s[30] = snap(30, cpu=99)
    r = DiagnosticEngine().analyze(s, [], disks(), {})
    assert r.counts["warning"] == 0 and r.counts["critical"] == 0
    assert any("spike" in f.title.lower() for f in r.findings)


def test_sustained_cpu_and_low_disk_flagged():
    r = DiagnosticEngine().analyze([snap(i, cpu=97) for i in range(60)], [], disks(3), {})
    sev = {f.category: f.severity for f in r.findings if f.severity in ("critical", "warning")}
    assert sev["CPU"] == "critical" and sev["Storage"] == "critical"
    assert r.health_score < 60


def test_short_window_downgrades_and_notes():
    r = DiagnosticEngine().analyze([snap(i, cpu=97) for i in range(5)], [], disks(), {})
    assert any(f.severity == "warning" and f.category == "CPU" for f in r.findings)
    assert any("preliminary" in n for n in r.notes)


def test_db_and_export_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        db = Database(os.path.join(d, "t.db"))
        rec = HistoryRecorder(db, interval=3)
        for i in range(10):
            rec.on_sample(snap(i, ts=time.time() - 100 + i))
        rec.flush()
        sm = db.summary(0)
        assert sm["n"] >= 3
        assert db.query_series(0)
        r = DiagnosticEngine().analyze([snap(i) for i in range(30)], [], disks(), {"hostname": "x"}, sm)
        rid = db.save_report(r)
        assert db.get_report(rid).health_score == r.health_score
        assert "SysTuklas" in report_to_text(r) and "<html" in report_to_html(r)
        for ext in (".txt", ".html", ".json"):
            export_report(r, os.path.join(d, "r" + ext))
        db.set_setting("a", "b"); assert db.get_setting("a") == "b"
        db.clear_history(); assert db.summary(0)["n"] == 0


def test_read_only_volumes_ignored():
    d = disks(0)
    d[0]["readonly"] = True
    r = DiagnosticEngine().analyze([snap(i) for i in range(30)], [], d, {})
    assert r.counts["critical"] == 0
