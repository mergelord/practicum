# Session context — MSFS health monitor PR #23/#24 follow-up

Date: 2026-06-07, night MSK.

## Reason

The user asked to verify PR #23 because it looked merged, but there was uncertainty whether the newest `msfs_health_monitor.py` version had actually reached `main`.

## Repository check

PR #23:

```text
https://github.com/mergelord/practicum/pull/23
Title: Add MSFS realtime health monitor
```

Status observed:

```text
state: closed
merged_at: 2026-06-06T22:50:45Z
```

However, the PR had been merged when its head was still:

```text
dfd46a80c430f4eabd3b8574e67d8f6f7083d80b
```

After that merge, the branch `speedlink-msfs-health-monitor` received newer commits, including:

```text
3ee64ff8dc84f91ec88af6c69b99a15ec5892c4f
f41a491a0bb6ab29c01784bd23d3102bda18f577
```

So `main` contained the older monitor version, while the branch contained the newer monitor version.

## What was missing from main

The older `main` version of `SPEEDLINK/msfs_health_monitor.py` had baseline monitoring:

```text
RAM
commit
pagefile
GPU / VRAM
MSFS process memory
event snapshot export
```

But it did not yet include the newest RAM/SSD/MSFS I/O additions:

```text
disk_read_mb_s
disk_write_mb_s
disk_queue_length
disk_avg_read_ms
disk_avg_write_ms

msfs_io_read_mb_s
msfs_io_write_mb_s
msfs_io_data_mb_s
```

These fields are important for the next MSFS 2020 test because the user specifically wants to see how intensively MSFS 2020 works with RAM and SSD.

## Fix

A new PR was opened to bring the latest monitor version into `main`:

```text
PR #24: Update MSFS health monitor with RAM and disk IO metrics
https://github.com/mergelord/practicum/pull/24
```

PR #24 uses the existing branch:

```text
speedlink-msfs-health-monitor
```

Latest branch commit at the time of this note:

```text
f41a491a0bb6ab29c01784bd23d3102bda18f577
```

## Current expected monitor behavior after PR #24

The monitor is intentionally focused on MSFS 2020 for now and detects:

```text
FlightSimulator.exe
```

It logs global/system metrics:

```text
CPU usage
RAM used / total / %
Committed Bytes / Commit Limit / %
Pagefile size
Total disk read / write MB/s
Total disk queue length
Total disk average read / write latency
NVIDIA GPU usage / temperature / power
Dedicated VRAM used / total / %
```

It also logs MSFS 2020 process-specific metrics:

```text
MSFS running / PID
MSFS working set memory
MSFS private memory
MSFS process I/O read MB/s
MSFS process I/O write MB/s
MSFS process I/O total data MB/s
```

## Why the disk/MSFS I/O fields matter

During the next real MSFS 2020 flight, the log should help separate these cases:

```text
1. Commit pressure / RAM issue:
   commit_used_percent approaches or exceeds ~85%.

2. MSFS memory growth:
   msfs_private_memory_gb grows continuously and does not stabilize.

3. SSD/disk bottleneck:
   disk_queue_length rises for a long time or disk_avg_read_ms / disk_avg_write_ms often exceeds ~50 ms.

4. MSFS-specific disk activity:
   msfs_io_read_mb_s / msfs_io_write_mb_s spikes during scenery loading or stutters.

5. Non-MSFS disk pressure:
   total disk activity is high while msfs_io_* is low, meaning another process may be loading the disk.

6. VRAM/NVIDIA path:
   vram_used_percent is near 90–95% and nvlddmkm appears near stutters/crashes.
```

## Files updated in the branch

```text
SPEEDLINK/msfs_health_monitor.py
SPEEDLINK/docs/msfs_health_monitor-instructions.md
SPEEDLINK/docs/session-2026-06-07-msfs-health-monitor.md
SPEEDLINK/docs/session-2026-06-07-msfs-health-monitor-pr24.md
```

## User-facing next step

Merge PR #24, then update local files in:

```text
C:\SPEEDLINK\NEWVER
```

Run:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\msfs_health_monitor.py
```

Then do a short dry test:

```text
Start logging
wait 20–30 seconds
Stop
Event snapshot
Open log folder
```

For the real flight, send:

```text
C:\SPEEDLINK\NEWVER\msfs_health_logs\msfs_health_YYYYMMDD_HHMMSS.csv
C:\SPEEDLINK\NEWVER\msfs_health_logs\event_snapshot_YYYYMMDD_HHMMSS.csv
```

## Current status

At the time this context was saved:

```text
PR #23: merged, but older monitor version reached main.
PR #24: open, contains the latest monitor with RAM/SSD/MSFS I/O metrics.
Notion: updated with the same context.
```