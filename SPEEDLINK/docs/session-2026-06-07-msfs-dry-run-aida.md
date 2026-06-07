# Контекст сессии: MSFS heavy-scene dry run, AIDA hardware report и предбоевой вывод

Дата: 2026-06-07, вечер MSK.

## Цель

Перед 2-часовым тестовым полётом в MSFS 2020 была проведена предбоевая проверка:

- короткий dry run `msfs_health_monitor.py` без MSFS;
- проверка pagefile / commit limit / crash dump / дисков;
- heavy-scene dry run с запущенным MSFS 2020, тяжёлым аддоном и тяжёлой сценой;
- анализ AIDA64 hardware report для точного понимания железа.

## Файлы, присланные пользователем

Heavy-scene MSFS dry run:

```text
msfs_health_20260607_162732.csv
event_snapshot_20260607_164620.csv
```

AIDA64 report:

```text
Report.htm
```

Ранее для baseline dry run также анализировались:

```text
msfs_health_20260607_161450.csv
event_snapshot_20260607_161546.csv
```

## Baseline dry run без MSFS

Короткий dry run монитора без MSFS подтвердил, что локальная версия `msfs_health_monitor.py` уже актуальная после PR #24: CSV содержит новые поля disk/MSFS I/O:

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

Baseline dry run:

```text
rows: 23
successful samples: 22
initial timeout: 1
RAM used: 16.626–19.645 GB
commit used: 25.852–29.249 GB
commit limit: 79.827 GB
commit used %: 32.385–36.640%
pagefile: 16.0 GB
disk queue: 0.0 throughout
disk avg read max: 20.231 ms
disk avg write max: 0.904 ms
GPU: NVIDIA GeForce RTX 4070 SUPER
VRAM: 3.503–3.718 / 11.994 GB
GPU temp: 42–44 C
```

Первый timeout был интерпретирован как неопасный warm-up PowerShell/Get-Counter, потому что все следующие сэмплы успешны.

## Pagefile / crash dump / disk mapping

Pagefile включён и постоянный:

```text
D:\pagefile.sys
AllocatedBaseSize=16384
CurrentUsage=0
PeakUsage=1
TempPageFile=FALSE
```

Crash dump:

```text
CrashDumpEnabled     : 3
DumpFile             : C:\WINDOWS\MEMORY.DMP
MinidumpDir          : C:\WINDOWS\Minidump
DedicatedDumpFile    :
AlwaysKeepMemoryDump :
```

Разметка дисков из `Get-Partition`:

```text
Disk 0 -> F: -> WDC WD10EAVS-00M4B0, старый 1 TB HDD
Disk 1 -> J: -> ST3500413AS, 500 GB HDD
Disk 2 -> E: -> WDC WD1002FAEX-00Y9A0, 1 TB HDD
Disk 3 -> C: -> Colorful CN600 256GB PRO, system SSD
Disk 4 -> D: -> DGSM4001TM63T, 1 TB SSD, pagefile
Disk 5 -> Z: -> Samsung SSD 980 1TB
Disk 6 -> R: -> KINGSTON SKC3000D2048G, 2 TB SSD
Disk 7 -> K: -> TOSHIBA THNSNH128GBST, 128 GB
```

Вывод:

```text
D:\pagefile.sys находится на Disk 4, а не на Disk 0.
```

Событие Windows:

```text
disk ID 51
\Device\Harddisk0\DR0 during a paging operation
```

относится к:

```text
Disk 0 / F: / WDC WD10EAVS-00M4B0
```

а не к диску с pagefile. Поэтому перед MSFS-тестом это не считалось блокером, если MSFS/Community/Official/Rolling Cache не лежат на `F:`.

## Heavy-scene MSFS dry run

Лог:

```text
msfs_health_20260607_162732.csv
```

Период:

```text
2026-06-07 16:27:32 -> 2026-06-07 16:46:16
```

Сэмплы:

```text
507 rows
507 successful samples
sample errors: none
MSFS running in 485 samples
```

### RAM / commit

```text
RAM total: 63.827 GB
RAM used: min 18.735 GB, mean 31.452 GB, max 39.042 GB
RAM used percent: min 29.352%, mean 49.277%, max 61.169%

commit limit: 79.827 GB
commit used: min 28.533 GB, mean 48.523 GB, max 57.595 GB
commit used percent: min 35.744%, mean 60.785%, max 72.150%

pagefile: 16.0 GB
```

Вывод: RAM и commit под тяжёлой сценой нагружены заметно, но не аварийно. До опасной зоны `commit_used_percent >= 85%` остаётся запас.

### MSFS process memory

```text
MSFS working set max: 16.474 GB
MSFS private memory max: 25.801 GB
```

Для тяжёлого аддона + тяжёлой сцены это много, но ожидаемо. По короткому heavy-scene dry run признаков утечки не видно; утечку нужно оценивать по 2-часовому логу.

### Disk / MSFS I/O

```text
disk_read_mb_s: min 0.000, mean 17.185, p95 30.031, max 2407.209
disk_write_mb_s: min 0.000, mean 1.413, p95 5.825, max 62.228
disk_queue_length: min 0.000, mean 0.041, p95 0.000, max 2.000
disk_avg_read_ms: min 0.000, mean 0.182, p95 0.454, max 6.094
disk_avg_write_ms: min 0.000, mean 0.184, p95 0.278, max 38.949

msfs_io_read_mb_s: min 0.000, mean 39.131, p95 172.401, max 2433.318
msfs_io_write_mb_s: min 0.000, mean 0.497, p95 1.483, max 21.310
msfs_io_data_mb_s: min 0.000, mean 39.627, p95 172.461, max 2434.079
```

Главный пик чтения:

```text
2026-06-07 16:33:59
system disk_read_mb_s ≈ 2407 MB/s
msfs_io_read_mb_s ≈ 2433 MB/s
```

Вывод: большие пики чтения похожи на нормальную загрузку сцены MSFS. Длительной очереди диска или длительных опасных задержек не видно.

### GPU / VRAM

```text
GPU utilization: max 99%
GPU temp: max 68°C
GPU power: max 196.110 W

VRAM total: 11.994 GB
VRAM used: min 0.924 GB, mean 9.054 GB, p95 11.451 GB, max 11.518 GB
VRAM used percent: min 7.702%, mean 75.483%, p95 95.471%, max 96.027%
```

Главный вывод: под тяжёлой сценой узкое место — VRAM. 12 GB RTX 4070 SUPER почти полностью забиты (`~96%`). Это не означает гарантированный вылет, но повышает риск фризов, stutter, `nvlddmkm` или графических проблем при ещё более тяжёлых участках/погоде/трафике/смене камеры.

### Event snapshot после heavy-scene dry run

Лог:

```text
event_snapshot_20260607_164620.csv
```

События:

```text
07.06.2026 16:00:05 System disk ID 51 Warning
An error was detected on device \Device\Harddisk0\DR0 during a paging operation.

07.06.2026 16:00:06 System volmgr ID 46 Error
Crash dump initialization failed!

Kernel-Power 172 / 125 informational events
```

Важно: эти события произошли до MSFS heavy-scene dry run:

```text
events: 16:00:05–16:00:10
MSFS heavy-scene log: 16:27:32–16:46:16
```

Во время heavy-scene dry run новых `nvlddmkm`, `Resource-Exhaustion`, `Application Error`, `Windows Error Reporting`, `disk`, `volmgr` событий не появилось.

## AIDA64 hardware context

Файл:

```text
Report.htm
```

Основная конфигурация:

```text
CPU: Intel Core i5-12600KF, 6P+4E / 16 threads
Motherboard: Gigabyte Z790 Gaming X AX
Chipset: Intel Raptor Point-S Z790 / Intel Alder Lake-S
BIOS: AMI, 2025-09-18
OS: Windows 10 Pro 22H2, build 19045.7291
RAM: 64 GB DDR5, 2x32 GB Kingston Fury KF552C40-32
Memory mode: Dual DDR5 SDRAM
Current memory speed: DDR5-5200, 40-40-40-80, CR 2T
GPU: Palit RTX 4070 Super / NVIDIA GeForce RTX 4070 SUPER
GPU chip: AD104-350-A1
GPU bus: PCI Express 4.0 x16, installed through CPU PCI-E 5.0 x16 port #2 @ x16
VRAM: 12282 MB reported by AIDA / 11.994 GB in monitor
NVIDIA driver: 581.08 / 32.0.15.8108, DCH, 2025-08-15
Display: Acer AL1720b 17-inch LCD
```

Storage from AIDA:

```text
Colorful CN600 256GB PRO      ~238 GB
DGSM4001TM63T                 ~953 GB
KINGSTON SKC3000D2048G        ~2048 GB, PCIe 4.0 x4
Samsung SSD 980 1TB           ~1000 GB, PCIe 3.0 x4
ST3500413AS                   500 GB, 7200 RPM, SATA-III
TOSHIBA THNSNH128GBST         128 GB, SATA-III
WDC WD1002FAEX-00Y9A0         1 TB, 7200 RPM, SATA-III
WDC WD10EAVS-00M4B0           1 TB, SATA-II
```

Temperatures in AIDA snapshot were normal:

```text
GPU Hotspot around 49°C
DIMM2 around 41°C
DIMM4 around 40°C
Colorful CN600 around 41/43°C
WDC WD10EAVS around 37°C
ST3500413AS around 37°C
Samsung SSD 980 around 42/50°C
WDC WD1002FAEX around 39°C
KINGSTON SKC3000 around 27/64°C
DGSM4001 around 40/37°C
TOSHIBA around 33°C
```

SMART summary in AIDA reports OK overall. For old HDDs, `OK` does not exclude brief wake/sleep stalls, SATA cable/controller quirks, or isolated event-log warnings.

## Current pre-flight verdict

For the planned 2-hour MSFS 2020 test flight:

```text
Можно лететь с монитором.
```

Reasons:

```text
CPU: OK
RAM: OK
commit limit: OK after pagefile enabled
pagefile: OK, D:\pagefile.sys 16 GB on Disk 4
Disk I/O: OK in heavy-scene dry run
GPU temperature: OK
No new critical Windows events during heavy-scene dry run
Speedlink/vJoy/HidHide chain previously stable
```

Main risk:

```text
VRAM pressure: RTX 4070 SUPER 12 GB reached ~96% VRAM usage in heavy scene.
```

If the goal is stress-testing the current configuration, keep settings unchanged and fly with the monitor running.

If the goal is maximum safety/stability, reduce one or more VRAM-heavy settings before the 2-hour flight:

```text
Texture Resolution
Terrain LOD
Object LOD
Traffic
Photogrammetry / scenery cache pressure
Aircraft-specific cockpit/display texture settings
```

## What to capture during the 2-hour flight

Run:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\msfs_health_monitor.py
```

In GUI:

```text
Start logging
fly 2 hours
Stop
Event snapshot
Open log folder
```

Send:

```text
msfs_health_*.csv
event_snapshot_*.csv
```

If symptoms occur, note approximate clock time:

```text
FPS drop
stutter/freeze
MSFS crash
black screen / driver reset
vJoy/control issue
```

Analyze after flight:

```text
vram_used_percent
commit_used_percent
ram_used_percent
msfs_private_memory_gb trend
msfs_working_set_gb trend
disk_queue_length
disk_avg_read_ms / disk_avg_write_ms
msfs_io_read_mb_s / write / data
nvlddmkm
Resource-Exhaustion-Detector
Application Error / Windows Error Reporting
disk / volmgr
Kernel-Power
```

Key thresholds:

```text
commit_used_percent >= 85% -> RAM/pagefile/commit pressure
vram_used_percent >= 90–95% + symptoms/nvlddmkm -> VRAM / graphics settings branch
disk_avg_read/write_ms > ~50 ms sustained -> storage/cache/scenery branch
disk_queue_length sustained > 1–2 -> storage bottleneck branch
msfs_private_memory_gb rising continuously across 2 hours -> possible memory growth/leak in MSFS/addons
```

## Related PRs / docs

Relevant previous PRs:

```text
PR #22: Windows health check context
PR #23: initial MSFS health monitor
PR #24: latest monitor with RAM/disk/MSFS I/O metrics
```

This session adds this context document:

```text
SPEEDLINK/docs/session-2026-06-07-msfs-dry-run-aida.md
```
