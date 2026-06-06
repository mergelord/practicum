# Session context — MSFS realtime health monitor

Date: 2026-06-07, night MSK.

## Reason

After Windows health checks showed that system files, component store, C: filesystem, and disk health were clean, and after the disabled pagefile was fixed, the next planned validation is a real MSFS flight.

The user asked whether a Python GUI could monitor all relevant runtime metrics and write logs for later analysis.

## Goal

Create a small Python GUI for use during real MSFS flights that monitors:

```text
CPU
RAM
Committed Bytes
Commit Limit
Pagefile size
NVIDIA GPU utilization
NVIDIA GPU temperature
NVIDIA GPU power
Dedicated VRAM used / total
MSFS process status and memory
Relevant Windows event snapshots
```

## Added tool

New file:

```text
SPEEDLINK/msfs_health_monitor.py
```

Instructions:

```text
SPEEDLINK/docs/msfs_health_monitor-instructions.md
```

## Logging

The monitor writes logs to:

```text
C:\SPEEDLINK\NEWVER\msfs_health_logs
```

CSV metrics log:

```text
msfs_health_YYYYMMDD_HHMMSS.csv
```

Event snapshot log:

```text
event_snapshot_YYYYMMDD_HHMMSS.csv
```

## Runtime dependencies

The monitor intentionally uses only:

```text
Python standard library
Tkinter
PowerShell
nvidia-smi, if available
```

No mandatory pip packages are required.

## What to watch during flight

### Commit

Healthy:

```text
Commit used is far below Commit limit
```

Warning:

```text
Commit used >= 85% Commit limit
```

### VRAM

Warning:

```text
Dedicated VRAM >= 90–95%
```

Especially important if MSFS stutters/crashes and `nvlddmkm` appears around the same time.

### GPU temperature

Warning threshold in GUI:

```text
GPU temp >= 83C
```

This is not an automatic failure, only a practical attention threshold.

## How to use for the next test

Before the daytime MSFS test:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\msfs_health_monitor.py
```

Then:

```text
1. Start logging.
2. Start/continue MSFS flight.
3. Stop logging after the flight.
4. Click Event snapshot.
5. Send msfs_health_*.csv and event_snapshot_*.csv for analysis.
```

## Analysis plan after logs are received

Compare the timeline of:

```text
Commit used / Commit limit
VRAM used / total
GPU temperature
GPU utilization
MSFS process memory
Windows events: nvlddmkm, Resource-Exhaustion, disk, volmgr, WER, Kernel-Power
```

Expected branches:

```text
If commit is high again -> memory/pagefile/commit pressure path.
If VRAM is pinned and nvlddmkm appears -> GPU/VRAM/MSFS graphics settings path.
If GPU temp is high -> cooling/power/clock path.
If all metrics are normal and no events -> current system baseline is stable.
```
