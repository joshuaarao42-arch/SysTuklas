# Understanding a SysTuklas Diagnostic Report

SysTuklas evaluates system measurements and presents findings with a severity, measured details, and (when useful) a suggested next step.

## Read the health score in context

The health score is a summary of the findings, not a hardware benchmark or a guarantee that every component is healthy. Read the individual findings and notes alongside the score.

## Severity levels

- **Critical:** A measurement crossed a serious threshold or the operating system reported a relevant problem. Review the recommended action promptly.
- **Warning:** A sustained condition may affect performance and deserves attention.
- **Notice / Info:** Useful context that is not necessarily a problem, such as moderate load or a brief spike.
- **Healthy / OK:** The measured condition is within the engine's normal range.

## Why sustained measurements matter

A short CPU spike can happen when an application opens, a page loads, or background work runs. SysTuklas considers averages and the share of time spent above thresholds instead of treating one high reading as proof of a fault.

Reports based on fewer than the minimum sample count are marked preliminary. Collect more measurements and run the analysis again before drawing conclusions from a short window.

## Storage and hardware notes

Read the drive's free-space details and the exact mount or drive named in the finding. Read-only volumes are excluded from ordinary free-space warnings because they can appear full by design.

High resource utilization is not, by itself, proof of failing hardware. SysTuklas distinguishes performance pressure from hardware problems reported by the operating system.

## Practical follow-up

1. Read the finding's measured detail, not only its title.
2. Check whether the condition is sustained or based on a short sample window.
3. Follow the suggested action and collect another report.
4. Compare reports taken under similar workloads.

A diagnostic report is a guide for investigation, not a substitute for professional hardware testing when a device shows physical symptoms or repeatedly fails.
