# Contributing to SysTuklas

SysTuklas is a Windows desktop tool for monitoring CPU, memory, storage, GPU, network, and process activity, then presenting diagnostic suggestions.

## Clone and run
```bash
git clone https://github.com/joshuaarao42-arch/SysTuklas.git
cd SysTuklas
pip install -r requirements.txt
python main.py
```
Use Windows 10 or 11 and Python 3.9 or newer, as described in the project README.

## Project-specific contributions
- CPU, memory, disk, GPU, network, and uptime monitoring.
- Process listing and resource-use information.
- Diagnostic rules and understandable recommendations.
- Performance history, charts, and CSV/PDF reports.
- Windows hardware information and optional WMI integration.
- Dashboard usability and graceful error handling.

## Monitoring accuracy and safety
Clearly distinguish measured values from estimates or unavailable sensor data. Handle missing permissions, unavailable hardware counters, and unsupported devices gracefully. Avoid presenting risky system changes as automatic fixes. Test idle and active workloads where possible and document the conditions. Never commit private process details, machine identifiers, logs, or personal system reports.

Use branches such as `feature/disk-health-panel` or `fix/cpu-usage-reading`. Include OS details, relevant hardware context, reproduction steps, and expected versus observed readings. Add screenshots for dashboard changes.
