# Session context: MSFS browser baseline preflight

Date: 2026-06-07 evening MSK.

This note records the final preflight baseline before a planned 2-hour MSFS 2020 flight. The user intentionally kept 2 browsers open with many tabs and wanted to know whether it was safe to fly without closing them.

## Files analyzed

```text
msfs_health_20260607_184721.csv
event_snapshot_20260607_185405.csv
```

Health log interval:

```text
2026-06-07 18:47:21 -> 2026-06-07 18:54:04
rows: 191
successful samples: 190
initial timeout: 1
MSFS running: false
```

The first sample reported:

```text
Windows metrics: timeout after 8.0s
```

This is treated as a non-blocking cold-start behavior of Windows metrics / PowerShell / Get-Counter because all following samples succeeded.

## Pagefile / commit context

Current pagefile state remains:

```text
D:\pagefile.sys
pagefile: 16.0 GB
commit limit: 79.827 GB
```

Increasing the pagefile was discussed. It can help only by increasing `commit limit` / virtual-memory headroom. It does not add physical RAM, does not reduce VRAM pressure, does not make MSFS faster, and cannot fix GPU/VRAM/disk problems.

For the current baseline, increasing pagefile is not required.

## RAM / commit baseline with browsers open

```text
RAM total: 63.827 GB
RAM used min/mean/max: 21.265 / 22.131 / 23.610 GB
RAM used percent min/mean/max: 33.317 / 34.674 / 36.990%

commit limit: 79.827 GB
commit used min/mean/max: 32.473 / 33.454 / 34.940 GB
commit used percent min/mean/max: 40.680 / 41.908 / 43.770%

pagefile: 16.0 GB
```

Conclusion: with 2 browsers and many tabs open, the machine is still far from dangerous commit pressure. The maximum observed `commit_used_percent` was 43.77%, while the warning threshold for flight analysis is `>= 85%`.

Previous heavy-scene MSFS dry run reached:

```text
commit used max: ~57.595 GB
commit used percent max: ~72.150%
```

Even allowing for browser load, the expected combined pressure is still acceptable for the flight. Keep pagefile at 16 GB for this test.

## Disk / SSD baseline

```text
disk_read_mb_s max: 11.707
disk_write_mb_s max: 43.213
disk_queue_length min/mean/max: 0.000 / 0.005 / 1.000
disk_avg_read_ms max: 3.721
disk_avg_write_ms max: 3.106
```

Conclusion: no background storage bottleneck is visible. Disk queue is effectively zero and read/write latency is low.

## GPU / VRAM baseline without MSFS

```text
GPU: NVIDIA GeForce RTX 4070 SUPER
GPU utilization max: 37%
GPU temp min/mean/max: 42 / 42.995 / 47 C
GPU power max: 43.090 W

VRAM total: 11.994 GB
VRAM used min/mean/max: 1.230 / 1.432 / 1.631 GB
VRAM used percent min/mean/max: 10.259 / 11.939 / 13.597%
```

Conclusion: without MSFS, GPU temperature and VRAM usage are normal.

The main risk for the upcoming flight is still MSFS-side VRAM pressure, not browser baseline load. Earlier heavy-scene MSFS testing reached about 96% VRAM usage on RTX 4070 SUPER 12 GB.

## FPS / PresentMon columns

The current CSV structure includes the FPS skeleton columns:

```text
fps_avg
fps_1pct_low
frametime_avg_ms
frametime_p99_ms
frametime_max_ms
frame_count
fps_source
```

For this baseline:

```text
fps_source: presentmon not found
frame_count: 0
fps_* / frametime_*: empty
```

This is expected because PresentMon was not installed/found. The FPS skeleton stays silent and does not affect core metrics.

## Event snapshot

`event_snapshot_20260607_185405.csv` did not show new critical events during the browser baseline.

Old events still present:

```text
07.06.2026 16:00:05 System disk ID 51 Warning
An error was detected on device \Device\Harddisk0\DR0 during a paging operation.

07.06.2026 16:00:06 System volmgr ID 46 Error
Crash dump initialization failed!
```

These occurred before the baseline and were already mapped to `Harddisk0 / Disk 0 / F: / WDC WD10EAVS-00M4B0`, not to `D:\pagefile.sys`.

No new `Resource-Exhaustion`, `nvlddmkm`, `Application Error`, `Windows Error Reporting`, fresh `disk`, or fresh `volmgr` events were found in this baseline.

## Preflight verdict

```text
OK to fly with current browsers open.
Do not increase pagefile before this flight.
```

Reasons:

```text
RAM: OK
commit: OK, max 43.77% in browser baseline
pagefile: OK, 16 GB, commit limit ~79.8 GB
disk: OK
GPU temperature: OK
VRAM baseline: OK
critical Windows events: no new events
```

Main risk for the 2-hour MSFS flight remains:

```text
VRAM pressure in MSFS: earlier heavy-scene test reached ~96% VRAM usage on RTX 4070 SUPER 12 GB.
```

If the flight shows stutter/freeze/black screen/driver reset/MSFS crash, first analysis branch should be VRAM / graphics settings / `nvlddmkm`; only then commit/pagefile/disk.

## Flight logging procedure

```powershell
cd C:\SPEEDLINK\NEWVER
python .\msfs_health_monitor.py
```

In the GUI:

```text
Start logging
fly 2 hours
Stop
Event snapshot
Open log folder
```

After the flight, collect:

```text
msfs_health_*.csv
event_snapshot_*.csv
```

If symptoms happen, record approximate time for correlation:

```text
FPS drop
stutter/freeze
MSFS crash
black screen / driver reset
vJoy/control issue
```
