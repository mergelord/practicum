# Session context — MSFS realtime health monitor

Date: 2026-06-07, night MSK.

## Reason

After Windows health checks showed that system files, component store, C: filesystem, and disk health were clean, and after the disabled pagefile was fixed, the next planned validation is a real MSFS 2020 flight.

The user asked whether a Python GUI could monitor all relevant runtime metrics and write logs for later analysis.

The user then clarified that testing is currently focused only on **MSFS 2020**, and that it is important to see how intensively MSFS 2020 uses RAM and SSD.

## Goal

Create a small Python GUI for use during real MSFS 2020 flights that monitors:

```text
CPU
RAM
Committed Bytes
Commit Limit
Pagefile size
Total disk read/write MB/s
Total disk queue length
Total disk average read/write latency
NVIDIA GPU utilization
NVIDIA GPU temperature
NVIDIA GPU power
Dedicated VRAM used / total
MSFS 2020 process status and memory
MSFS 2020 process I/O read/write/data MB/s
Relevant Windows event snapshots
```

## MSFS version detection

Current target process:

```text
FlightSimulator.exe
```

So the monitor is intentionally MSFS 2020-focused for now. It does not try to detect MSFS 2024-specific process names yet.

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

## RAM and commit analysis

The monitor logs both global memory state and MSFS process memory:

```text
ram_used_gb
ram_total_gb
ram_used_percent
commit_used_gb
commit_limit_gb
commit_used_percent
msfs_working_set_gb
msfs_private_memory_gb
```

Important distinction:

```text
RAM used            = physical RAM currently used by Windows overall.
Commit used / limit = virtual memory promise pressure, affected by RAM + pagefile.
MSFS private memory = memory owned by FlightSimulator.exe.
```

Healthy:

```text
Commit used is far below Commit limit
MSFS memory grows during loading, then stabilizes during flight
```

Warning:

```text
Commit used >= 85% Commit limit
MSFS private memory grows continuously without stabilizing
```

## SSD / disk analysis

The monitor logs global disk counters:

```text
disk_read_mb_s
disk_write_mb_s
disk_queue_length
disk_avg_read_ms
disk_avg_write_ms
```

And MSFS process I/O counters:

```text
msfs_io_read_mb_s
msfs_io_write_mb_s
msfs_io_data_mb_s
```

This allows separating:

```text
1. MSFS itself is loading/streaming/writing heavily.
2. Some other process is loading the disk while MSFS is affected.
```

Warning signs:

```text
Disk queue stays high for a long time.
Disk average read/write latency often exceeds ~50 ms.
MSFS stutters line up with disk latency or queue spikes.
```

## VRAM and NVIDIA analysis

Warning:

```text
Dedicated VRAM >= 90–95%
```

Especially important if MSFS stutters/crashes and `nvlddmkm` appears around the same time.

## GPU temperature

Warning threshold in GUI:

```text
GPU temp >= 83C
```

This is not an automatic failure, only a practical attention threshold.

## How to use for the next test

Before the daytime MSFS 2020 test:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\msfs_health_monitor.py
```

Then:

```text
1. Start logging.
2. Start/continue MSFS 2020 flight.
3. Stop logging after the flight.
4. Click Event snapshot.
5. Send msfs_health_*.csv and event_snapshot_*.csv for analysis.
```

## Analysis plan after logs are received

Compare the timeline of:

```text
Commit used / Commit limit
RAM used / total
MSFS working set / private memory
Total disk read/write / queue / latency
MSFS process I/O read/write/data
VRAM used / total
GPU temperature
GPU utilization
Windows events: nvlddmkm, Resource-Exhaustion, disk, volmgr, WER, Kernel-Power
```

Expected branches:

```text
If commit is high again -> memory/pagefile/commit pressure path.
If MSFS private memory grows endlessly -> MSFS/addon memory growth path.
If disk latency/queue spikes match stutters -> SSD/disk/cache/pagefile/scenery loading path.
If VRAM is pinned and nvlddmkm appears -> GPU/VRAM/MSFS graphics settings path.
If GPU temp is high -> cooling/power/clock path.
If all metrics are normal and no events -> current system baseline is stable.
```
