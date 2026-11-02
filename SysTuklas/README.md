# SysTuklas — Computer Performance Diagnostic and Monitoring System

*Tuklas* means "to discover / investigate". SysTuklas does not just list numbers like Task Manager:
it **records history**, **analyses sustained behaviour** and **explains what it found in plain language with
concrete recommendations**.

## Install (Windows 10/11)

1. Install Python 3.10+ from python.org (tick **"Add Python to PATH"**; keep the *tcl/tk* option ticked).
2. Open a terminal in this folder and run:

```
pip install -r requirements.txt
python main.py
```
(or double-click `run_systuklas.bat`).

Optional standalone `.exe`: `pip install pyinstaller` then run `build_exe.bat`.
Run as **Administrator** only if you need to end protected processes.

## Features

| Page | What it does |
|---|---|
| Dashboard | CPU / RAM / drive / network cards, live chart, hardware summary, top processes, last health score |
| CPU | Utilization, frequency, cores/threads, temperature (if exposed), per-thread load, history charts |
| Memory | Total / used / available, swap, pressure badge, **applications grouped by total memory** |
| Processes | Search, sort (header click or menu), details dialog, **End process with confirmation** (protected system processes blocked / extra warning) |
| Storage | Per-drive capacity cards, read/write activity, drive table, physical disk health from Windows |
| Network | Upload/download speed, session and since-boot totals, adapters, connection count |
| Diagnostics | Health score 0–100, findings (Critical / Warning / Notice / Healthy) with recommendations, export TXT / HTML / JSON |
| History | SQLite history (1 h – 30 d), usage / disk I/O / network charts, CSV export, chart PNG, saved reports |

## How the diagnostic engine avoids false alarms

* Uses **averages and share-of-time over a window** (up to 5 minutes live + 24 h of stored history), not single readings.
* Brief spikes are reported as *"Short CPU spikes (normal)"*, not problems.
* A hardware problem is reported **only if Windows itself reports one** (drive health status). High usage is never called a failure.
* Reads from a very short window are marked *preliminary*.
* Persistent patterns from history ("memory pressure is consistent, not a one-off") raise the severity; one-off busy moments do not.
* Missing sensors (e.g. temperature on Windows) are noted, never treated as errors.

## Architecture

```
main.py
systuklas/
  core/                    (no GUI code)
    models.py              Snapshot, Finding, DiagnosticReport
    monitor.py             SystemMonitor + ProcessSampler (background threads), hardware info
    database.py            SQLite storage, HistoryRecorder (10 s averages, 30-day retention)
    diagnostics.py         DiagnosticEngine (rules, scoring, recommendations)
    exporter.py            TXT / HTML / JSON reports, CSV history
    formatting.py
  ui/
    app.py                 Main window, sidebar (collapses to icons on narrow windows), page manager
    theme.py icons.py      Dark theme; Pillow-drawn icons
    widgets.py dialogs.py  Cards, responsive grid, live/history charts (Matplotlib), sortable table, dialogs
    pages/                 dashboard, cpu, memory, processes, storage, network, diagnostics, history
tests/test_core.py         pytest tests for the engine and database
```

The GUI never calls slow system functions: monitoring runs on daemon threads, the UI only reads the latest
results on a 1-second timer, and database / scan / PowerShell work uses a worker thread with a polling callback.

Data is stored in `%APPDATA%\SysTuklas\systuklas.db`.

## Known limitations

* Detailed SMART attributes and CPU temperature are not available through Windows without vendor drivers;
  SysTuklas reports what the OS exposes and says so when something is unavailable.
* Per-process network usage is not provided by psutil.

## Tests
`pip install pytest` then `pytest tests`
