# Session context — MSFS 2024 validation and X-Plane 12 monitor support

Date: 2026-06-09 → 2026-06-10 MSK  
Project: `SPEEDLINK`

## Summary

This session validated the updated simulator health monitor with Microsoft Flight Simulator 2024 and prepared it for X-Plane 12.

Main outcomes:

- `SPEEDLINK/msfs_health_monitor.py` now detects MSFS 2024 via `FlightSimulator2024`.
- MSFS 2024 was tested for ~2h24m on Ultra graphics with heavy add-ons.
- The system handled both MSFS 2020 and MSFS 2024 heavy scenarios.
- X-Plane 12 process name was confirmed as `X-Plane`.
- A PR was opened to generalize the monitor UI and add X-Plane 12 detection.

## PRs

### PR #31 — MSFS 2024 process detection

```text
https://github.com/mergelord/practicum/pull/31
branch: msfs-2024-health-monitor-detection
commit: 5e5fe48f32d1629059755c38e581e4e354c69e38
file: SPEEDLINK/msfs_health_monitor.py
```

Changes:

- Detects `FlightSimulator2024` as `MSFS 2024`.
- Keeps `FlightSimulator` as `MSFS 2020`.
- Prefers MSFS 2024 when both are open.
- Resolves PerfProc process I/O counters by PID via `IDProcess`.
- Adds/logs `msfs_version`, `msfs_process_name`, and `msfs_path`.
- GUI shows version/process/PID/path.

### PR #32 — X-Plane 12 health monitor support

```text
https://github.com/mergelord/practicum/pull/32
branch: support-xplane12-health-monitor
file: SPEEDLINK/msfs_health_monitor.py
```

Changes:

- UI title changed to `Flight Sim Health Monitor`.
- Added X-Plane 12 detection:
  - `X-Plane` -> `X-Plane 12`
- Kept MSFS support:
  - `FlightSimulator2024` -> `MSFS 2024`
  - `FlightSimulator` -> `MSFS 2020`
- Kept PID-based PerfProc I/O mapping.
- Avoided detecting X-Plane by `MainWindowTitle`, because `dwm.exe` can also expose `MainWindowTitle = X-Plane`.
- GUI labels are more generic:
  - `Simulator`
  - `Sim path`
  - `Sim I/O`
- New logs are written to `sim_health_logs`.
- New CSV files use `sim_health_YYYYMMDD_HHMMSS.csv`.
- Syntax was checked with `python -m py_compile`.

## Confirmed process names

### MSFS 2024

User confirmed:

```text
ProcessName: FlightSimulator2024
MainWindowTitle: Microsoft Flight Simulator 2024 - 1.7.32.0
Path: C:\Program Files\WindowsApps\Microsoft.Limitless_1.7.32.0_x64__8wekyb3d8bbwe\FlightSimulator2024.exe
```

### X-Plane 12

User confirmed:

```text
ProcessName    Id     MainWindowTitle    Path
dwm            1716   X-Plane            C:\WINDOWS\system32\dwm.exe
X-Plane        38420  X-Plane            D:\XP12\X-Plane.exe
```

Important implementation note:

```text
Detect X-Plane 12 by ProcessName = X-Plane.
Do not detect it by MainWindowTitle, because dwm.exe can also show title X-Plane.
```

## Short MSFS 2024 baseline

Files:

```text
msfs_health_20260609_195754.csv
event_snapshot_20260609_201656.csv
```

Observed:

```text
duration: ~18 min 57 sec
rows: 428
MSFS running: ~18 min 15 sec
detected version: MSFS 2024
process: FlightSimulator2024
PID: 37004
commit_limit_gb: ~95.827
pagefile_gb: 32.0
commit peak: ~70.319 GB / 73.4%
RAM peak: ~41.725 GB / 65.4%
VRAM peak: ~11.260 GB / 93.9%
GPU temp max: 69°C
```

Conclusion:

- MSFS 2024 detection worked.
- RAM/commit/pagefile/GPU temperature were OK.
- VRAM usage was high but expected for heavy Ultra scenarios.

## Long MSFS 2024 test

Files:

```text
msfs_health_20260609_203420.csv
event_snapshot_20260609_225822.csv
```

Conditions:

```text
MSFS 2024
Ultra graphics settings
heavy add-ons
```

Duration:

```text
log: 20:34:20 -> 22:58:17
duration: ~143.95 min
MSFS running: ~143.8 min
rows: 3385
process: FlightSimulator2024
PID: 37572
```

### Commit / pagefile

```text
commit_limit_gb: 95.827
pagefile_gb: 32.0
commit avg: 67.761 GB / 70.7%
commit p95: 71.757 GB / 74.9%
commit p99: 73.563 GB / 76.8%
commit max: 79.899 GB / 83.378%
minimum headroom at peak: ~15.928 GB
```

Threshold counts:

```text
commit > 70%: 1829 samples
commit > 75%: 147 samples
commit > 80%: 16 samples
commit > 85%: 0
commit > 90%: 0
```

Conclusion:

```text
The 32/64 GB pagefile on D: provides enough commit limit headroom.
MSFS 2024 did not enter the 85–90% critical commit zone.
```

### RAM

```text
RAM total: 63.827 GB
RAM avg: 31.537 GB / 49.4%
RAM p95: 36.682 GB / 57.5%
RAM max: 49.520 GB / 77.6%
RAM > 80%: 0 samples
```

Conclusion: physical RAM is OK.

### Simulator process memory

```text
working set avg/max: 9.814 / 16.193 GB
private memory avg/max: 24.849 / 29.852 GB
private memory > 28 GB: 101 samples
private memory > 30 GB: 0 samples
```

By the end of the log, simulator private memory decreased:

```text
first: 23.690 GB
last: 17.278 GB
delta: -6.412 GB
```

Conclusion: no obvious runaway memory leak in this test.

### VRAM

```text
GPU: NVIDIA GeForce RTX 4070 SUPER
VRAM total: 11.994 GB
VRAM avg: 10.238 GB / 85.4%
VRAM p95: 10.747 GB / 89.6%
VRAM p99: 10.974 GB / 91.5%
VRAM max: 11.451 GB / 95.473%
```

Threshold counts:

```text
VRAM > 80%: 2857 samples
VRAM > 90%: 117 samples
VRAM > 95%: 2 samples
VRAM > 98%: 0
```

Conclusion:

```text
VRAM is the main practical limit with Ultra + heavy add-ons.
The short 95.47% peak did not cause a failure.
```

### GPU

```text
GPU util avg/p95/max: 55.5% / 75% / 95%
GPU temp avg/p95/max: 58.25°C / 63°C / 68°C
GPU power avg/max: 124 W / 174 W
GPU temp > 70°C: 0
```

Conclusion: GPU thermals are excellent.

### Disk / I/O

```text
disk_read avg/max: 1.407 / 101.169 MB/s
disk_write avg/max: 2.703 / 372.069 MB/s
disk_queue avg/max: 0.028 / 4
disk_avg_read_ms p95/max: 0.599 / 351.028 ms
disk_avg_write_ms p95/max: 0.196 / 47.257 ms
```

Most notable storage episode:

```text
22:30:52 -> 22:31:55
~63 sec with queue >= 1
read latency peak: 351.028 ms
write latency peak: 47.257 ms
```

Conclusion:

- Storage generally handled the test.
- One short latency/queue spike remains worth observing.
- If a freeze occurred around 22:31, disk/background I/O/pagefile/cache is a likely correlate.

### CPU

```text
CPU avg/p95/max: 39.2% / 50.1% / 80.8%
```

Conclusion: no system-wide CPU bottleneck was visible.

### Event snapshot

The event snapshot contained the same old event:

```text
disk Event ID 51 at 09.06.2026 16:56:17
\Device\Harddisk0\DR0 during paging operation
```

This event happened before the MSFS 2024 flight. No new critical events appeared during the MSFS 2024 test window.

## Combined MSFS 2020 + MSFS 2024 conclusion

Both simulators were tested under heavy real-world conditions:

```text
MSFS 2020: Ultra + heavy add-ons + 3+ hours — system handled it.
MSFS 2024: Ultra + heavy add-ons + ~2h24m — system handled it.
```

Overall system status:

```text
CPU: OK
RAM: OK
commit limit/pagefile: OK
GPU temperature: OK
VRAM: high usage, main practical limit
SSD/I/O: generally OK, short spikes to observe
Speedlink/vJoy/HidHide: stable
```

Key system conclusion:

```text
64 GB RAM + D:\pagefile.sys 32/64 GB provide sufficient commit limit.
Without pagefile, MSFS 2024 could have been close to the commit limit ceiling.
```

## X-Plane 12 validation plan after PR #32 merge

After merging PR #32:

1. Update local project files.
2. Launch X-Plane 12.
3. Start the monitor:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\msfs_health_monitor.py
```

4. Verify GUI shows:

```text
Simulator: X-Plane 12 pid=... proc=X-Plane
Sim path: D:\XP12\X-Plane.exe
Sim I/O: read/write/total
```

5. Run a short 3–5 minute baseline.
6. Save:
   - `sim_health_*.csv`
   - `event_snapshot_*.csv`

## X-Plane 12 analysis focus

Use the same key metrics:

```text
commit_used_percent
ram_used_percent
vram_used_percent
gpu_temp_c
disk_queue_length
disk_avg_read_ms / disk_avg_write_ms
msfs_private_memory_gb  # legacy column name, now simulator private memory
msfs_io_read_mb_s / write / data  # legacy column name, now simulator I/O
```

For X-Plane 12 with heavy scenery/ortho/mesh, especially watch:

```text
VRAM pressure
commit limit/headroom
disk latency spikes
sim process I/O read bursts
```

## CSV compatibility note

PR #32 keeps legacy CSV field names for compatibility:

```text
msfs_running
msfs_version
msfs_process_name
msfs_pid
msfs_path
msfs_working_set_gb
msfs_private_memory_gb
msfs_io_read_mb_s
msfs_io_write_mb_s
msfs_io_data_mb_s
```

For X-Plane 12 they will contain:

```text
msfs_version = X-Plane 12
msfs_process_name = X-Plane
msfs_path = D:\XP12\X-Plane.exe
```

This preserves older analysis scripts. A future change may add duplicate `sim_*` fields, but it is not required for the current tests.