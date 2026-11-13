# Measurements

Only measured numbers go here (date, setup, method). Source for the pitch and the criteria check in [PLAN.md](../PLAN.md#hackathon-criteria-check). Method: [WIRING.md](../WIRING.md#energy-measurement-with-the-peaktech); software values come from `app/logs/metrics.csv` (MetricsLogger).

## Power and energy

| State | Voltage (V) | Current (A) | Power (W) | Date / setup | Notes |
| --- | --- | --- | --- | --- | --- |
| Idle (display off, mic off) | | | | | |
| Menu | | | | | |
| Round, nobody speaking | | | | | |
| Round, speaking | | | | | |

- Energy per round (mean power × round time): _ Wh
- Saving from VAD gating (round with speech-to-text always on vs. gated): _ %

## Latency (end of speech to command, from metrics.csv `command_latency_ms`)

| Tries | Median (ms) | Worst (ms) | Date / setup |
| --- | --- | --- | --- |
| | | | |

## Memory and CPU (from `free -m` and metrics.csv)

| State | MemAvailable (MB) | Process RSS (MB) | CPU (%) |
| --- | --- | --- | --- |
| Idle | | | |
| Menu | | | |
| Round, nobody speaking | | | |
| Round, speaking | | | |
