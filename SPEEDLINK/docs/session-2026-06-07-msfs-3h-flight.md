# Session context: successful 3-hour MSFS flight

Date: 2026-06-07 night MSK.

This document records the analysis of a successful long MSFS 2020 flight after the Speedlink/vJoy/HidHide setup and MSFS health monitor work.

## Files analyzed

```text
msfs_health_20260607_193438.csv
event_snapshot_20260607_230506.csv
```

Health log interval:

```text
2026-06-07 19:34:38 -> 2026-06-07 23:05:04
duration: ~3.51 hours
rows: 5225
sample_ok: 5211
sample errors: 14
```

All 14 sample errors were:

```text
Windows metrics: timeout after 8.0s
```

These appeared periodically, roughly every 16 minutes, and are treated as non-blocking Windows metrics / PowerShell / Get-Counter timeouts. The monitor recovered and continued logging normally.

## Flight result

The user reported that the 3-hour flight completed successfully.

Verdict:

```text
MSFS 2020 3+ hour flight: successful
Speedlink/vJoy/HidHide chain: stable
Windows stability during flight: OK
```

## Event snapshot

`event_snapshot_20260607_230506.csv` contained only old events from around 16:00:

```text
07.06.2026 16:00:05 System disk ID 51 Warning
An error was detected on device \Device\Harddisk0\DR0 during a paging operation.

07.06.2026 16:00:06 System volmgr ID 46 Error
Crash dump initialization failed!
```

No new critical events appeared during the flight:

```text
nvlddmkm: none
Resource-Exhaustion: none
Application Error: none
Windows Error Reporting: none
fresh disk/volmgr: none
Kernel-Power 41: none
```

This is a strong positive stability signal.

## RAM

During MSFS:

```text
RAM used min: 20.325 GB
RAM used mean: 29.496 GB
RAM used max: 40.834 GB
RAM used percent max: 63.976%
```

Conclusion:

```text
Physical RAM is OK.
64 GB RAM is enough for this scenario.
No physical RAM exhaustion was observed.
```

## Commit / pagefile

During MSFS:

```text
commit used min: 31.219 GB
commit used mean: 63.630 GB
commit used max: 76.172 GB
commit_used_percent max: 89.852%
```

Threshold counts:

```text
commit_used_percent >= 70%: 4971 samples
commit_used_percent >= 80%: 2331 samples
commit_used_percent >= 85%: 388 samples
```

The pre-defined warning threshold was:

```text
commit_used_percent >= 85%
```

The flight succeeded, but commit pressure was clearly high.

Important detail:

```text
commit_limit_gb max: 84.890
pagefile_gb max: 21.062
```

Although the configured pagefile baseline was 16 GB, Windows appears to have temporarily expanded the pagefile / commit limit during the flight.

Updated conclusion:

```text
16 GB pagefile survived the test, but it is now considered borderline for this MSFS + browsers + addons scenario.
```

Recommended follow-up:

```text
D:\pagefile.sys
Initial size: 32768 MB
Maximum size: 65536 MB
```

Then reboot and re-check pagefile / commit limit.

This recommendation is about commit limit / virtual memory headroom, not physical RAM capacity. It does not mean 64 GB RAM is insufficient.

## MSFS process memory

MSFS private memory:

```text
min: 0.174 GB
mean: 23.830 GB
max: 32.288 GB
```

MSFS working set:

```text
mean: 7.950 GB
max: 22.180 GB
```

Peak private memory occurred around:

```text
2026-06-07 19:49:40 -> 32.288 GB
```

Conclusion:

```text
MSFS/addon memory footprint was high but survived.
No obvious fatal memory runaway to crash was proven by this log.
```

Memory remained heavy enough to justify a larger pagefile safety margin.

## GPU / VRAM

RTX 4070 SUPER 12 GB:

```text
VRAM total: 11.994 GB
VRAM used mean: 9.925 GB
VRAM used max: 11.465 GB
VRAM used percent max: 95.587%
```

Threshold counts:

```text
VRAM >= 90%: 1340 samples
VRAM >= 95%: 12 samples
VRAM >= 98%: 0 samples
```

GPU:

```text
GPU utilization max: 100%
GPU temp max: 71 C
GPU power max: 196.590 W
```

Conclusion:

```text
VRAM pressure was high but survived.
GPU thermals are excellent.
No NVIDIA driver reset appeared in the event log.
```

If future flights show stutter/freeze/black screen/driver reset/MSFS crash, first analysis branch remains VRAM / graphics settings / `nvlddmkm`.

## Disk / SSD

Overall disk metrics were acceptable:

```text
disk_queue_length mean: 0.098
disk_avg_read_ms mean: 0.934 ms
disk_avg_write_ms mean: 0.770 ms
```

There were short spikes:

```text
disk_queue_length max: 7
disk_avg_read_ms max: 201.847 ms
disk_avg_write_ms max: 119.776 ms
```

Threshold counts:

```text
disk_avg_read_ms >= 50 ms: 21 samples
disk_avg_write_ms >= 50 ms: 26 samples
disk_queue_length >= 2: 150 samples
```

Most notable window:

```text
~22:19 -> ~22:27
```

In that window disk queue and latency spikes were visible. They did not cause a crash. Some spikes did not align with high `msfs_io_*`, so the source may have been Windows/background/browser/cache/pagefile/antivirus/another process rather than MSFS alone.

Conclusion:

```text
Disk is generally OK, but short latency spikes should remain under observation.
```

If the user noticed stutters around 22:19-22:27, disk latency is a plausible correlating signal.

## FPS / PresentMon

The CSV contains FPS skeleton fields:

```text
fps_avg
fps_1pct_low
frametime_avg_ms
frametime_p99_ms
frametime_max_ms
frame_count
fps_source
```

For this flight:

```text
fps_source: presentmon not found
frame_count: 0
fps_* / frametime_*: empty
```

This is expected: PresentMon was not installed/found. The FPS skeleton did not affect the core metrics.

## Stability summary

Green:

```text
3+ hour MSFS flight completed successfully
Windows event snapshot clean for flight window
nvlddmkm: none
Resource-Exhaustion: none
GPU temp: OK, max 71 C
physical RAM: OK, max ~64%
Speedlink/vJoy/HidHide: stable in real flight
```

Yellow / observe:

```text
commit_used_percent max: 89.852%
pagefile grew temporarily to ~21 GB
VRAM max: 95.587%
disk latency spikes around 22:19-22:27
```

No red failure was observed:

```text
no crash
no driver reset
no Resource-Exhaustion
no Kernel-Power 41
```

## Updated operational recommendation

The current setup is considered stable for long MSFS 2020 flights, but pagefile should be increased for safety:

```text
D:\pagefile.sys
Initial size: 32768 MB
Maximum size: 65536 MB
```

Reboot after changing pagefile.

Do not change NVIDIA driver or reduce MSFS graphics settings solely based on this successful flight. If future symptoms appear, investigate in this order:

```text
1. VRAM / graphics settings / nvlddmkm
2. commit/pagefile pressure
3. disk latency / background I/O
```

## Final status after this flight

```text
Speedlink/vJoy/HidHide: stable
MSFS 2020 3-hour flight: successful
Windows stability: OK
GPU thermal: OK
VRAM: high but survived
RAM: OK
Commit/pagefile: needs larger safety margin
Disk: generally OK, short latency spikes to observe
```
