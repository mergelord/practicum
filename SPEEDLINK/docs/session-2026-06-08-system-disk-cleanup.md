# Session context — 2026-06-08 — system disk cleanup, pagefile and disk benchmarks

Date: 2026-06-08, night MSK.
Status: C: system disk cleanup reached the safe lower target; further cleanup is postponed.

## Summary

After the successful 3+ hour MSFS 2020 flight and high `commit_used_percent` observations, this session focused on:

- increasing pagefile / commit limit headroom;
- benchmarking disks used by MSFS and pagefile;
- cleaning the system SSD `C:` after low sequential write speed was observed while the disk was highly filled;
- conservatively removing only explicitly approved application leftovers.

Final state:

```text
C: FreeSpace=49515089920 bytes
C: Size=255257083904 bytes
≈46.12 GiB free
≈49.52 decimal GB free
```

The immediate `45+ GiB` free-space target was reached. The system is now in the lower part of the preferred `45–50 GiB` band. Long-term target remains `60+ GiB`, but there is no immediate disk-space emergency.

## Pagefile / commit limit

Recommended and applied pagefile setting:

```text
D:\pagefile.sys
Initial size: 32768 MB
Maximum size: 65536 MB
```

Verification under extra browser + 4K video load:

```text
TotalVirtualMemorySize=100482056 KB
FreeVirtualMemory=66216196 KB
D:\pagefile.sys
AllocatedBaseSize=32768
CurrentUsage=0
PeakUsage=1
TempPageFile=FALSE
```

Derived values:

```text
Commit limit: ~95.83 GB
Used commit: ~32.68 GB
Headroom: ~63.15 GB
Commit used: ~34.1%
```

Conclusion: the 32/64 GB pagefile gives strong commit-limit headroom. This is about Windows commit limit, crash dumps, Windows Error Reporting and heavy scenarios like MSFS + browsers + companion apps — not about physical 64 GB RAM being insufficient.

## CrystalDiskMark results

Tested disks:

```text
R: KINGSTON SKC3000D2048G 2TB — MSFS disk
D: DGSM4001TM63T 1TB — pagefile disk
C: Colorful CN600 256GB PRO — system SSD
```

### R: MSFS disk

```text
SEQ 1MiB Q8T1 Read: 6903.395 MB/s
SEQ 1MiB Q8T1 Write: 6840.429 MB/s
RND 4KiB Q32T16 Read: 1581.851 MB/s / 386194.1 IOPS
RND 4KiB Q32T16 Write: 1671.975 MB/s / 408197.0 IOPS
```

### D: pagefile disk

```text
SEQ 1MiB Q8T1 Read: 7037.671 MB/s
SEQ 1MiB Q8T1 Write: 6666.583 MB/s
RND 4KiB Q32T16 Read: 1570.556 MB/s / 383436.5 IOPS
RND 4KiB Q32T16 Write: 1628.096 MB/s / 397484.4 IOPS
```

### C: before cleanup

Initial C: result was suspiciously low on sequential write:

```text
C: 88% used
SEQ 1MiB Q8T1 Read: 2527.980 MB/s
SEQ 1MiB Q8T1 Write: 74.575 MB/s
```

### C: after cleanup

After freeing space, C: normalized:

```text
C: 82% used
SEQ 1MiB Q8T1 Read: 3251.137 MB/s
SEQ 1MiB Q8T1 Write: 1985.214 MB/s
RND 4KiB Q32T16 Read: 1897.756 MB/s / 463319.3 IOPS
RND 4KiB Q32T16 Write: 922.778 MB/s / 225287.6 IOPS
```

Conclusion: the low C: write result was most likely related to high fill level, SLC cache / background write pressure, or background activity. It is not proof of SSD failure.

## C: cleanup work

Approximate starting point from TreeSize:

```text
C: free ~27.9 GB
```

Final result:

```text
FreeSpace=49515089920 bytes
Size=255257083904 bytes
≈46.12 GiB free
≈49.52 decimal GB free
```

### Main cleanup stages

- `cleanup_appdata_safe.ps1` freed almost nothing because selected AppData cache targets were already absent or locked. This was not considered a script failure.
- `cleanup_c_no_root_tools.ps1` was created to avoid touching the user's root utility folders.
- Cleaned or moved safe caches/installers:
  - `C:\ProgramData\iFlyManager\downloads\*.zip`;
  - Samsung Magician setup backup;
  - LittleNavMap non-MSFS DBs;
  - X-Dispatch `xplane-data.db`;
  - HuggingFace cache;
  - Verdent / SimBrief updater installers;
  - pip cache;
  - SimToolkitPro cache / `.nupkg`;
  - Jeppesen `TerminalCharts.alt` / `.0` were first renamed to backups, then deleted after Jeppesen was confirmed working.
- Removed through uninstall flow from `C:\Program Files`:
  - Altova;
  - 4K Download components.
- Removed through uninstall flow from `C:\Program Files (x86)`:
  - AOMEI Backupper / AOMEI;
  - Epic Games;
  - Hotspot Shield;
  - HiroVpn;
  - OkayFreedom.

## Program Files (x86) leftovers and permissions

After uninstalling selected x86 apps, leftovers remained:

```text
C:\Program Files (x86)\AOMEI
C:\Program Files (x86)\Epic Games
C:\Program Files (x86)\Hotspot Shield
```

Measured leftover size before manual cleanup:

```text
Count: 1322
Sum: 539821949 bytes
≈514.8 MiB
```

Initial `Remove-Item` freed only a small amount and left folders behind. Verbose deletion of AOMEI showed permission errors on old Backupper logs:

```text
C:\Program Files (x86)\AOMEI\AOMEI Backupper 6.0.0\log\ABService*.txt
Access to the path is denied.
```

Resolution in elevated PowerShell:

```powershell
takeown /F "C:\Program Files (x86)\AOMEI" /R /D Y
icacls "C:\Program Files (x86)\AOMEI" /grant Administrators:F /T
Remove-Item "C:\Program Files (x86)\AOMEI" -Recurse -Force

Remove-Item "C:\Program Files (x86)\Epic Games" -Recurse -Force
Remove-Item "C:\Program Files (x86)\Hotspot Shield" -Recurse -Force
```

Follow-up `Remove-Item` for AOMEI and Epic Games returned `Cannot find path`, which in this context means the folders were already removed. Hotspot Shield deleted silently.

Free space after leftover cleanup:

```text
FreeSpace=49515089920
Size=255257083904
```

## Explicit do-not-touch list

The user explicitly said not to touch these root utility folders:

```text
C:\[Guru3D.com]-DDU
C:\FRST
C:\Win_10-11
C:\WININSTALL
C:\SysinternalsSuite
C:\KVRT2020_Data
C:\KVRT_Data
C:\gsmartcontrol-1.1.3-win64
C:\bluescreenview-x64
C:\Windows Update MiniTool 22.04.2022 Portable
C:\TCPU74
C:\TCPU75
```

Also do not touch without explicit confirmation:

```text
GIGABYTE
Windows Kits
Microsoft / Microsoft Visual Studio
Steam
Common Files
Google
Java
NVIDIA Corporation
dotnet
Intel
MSI Afterburner
RivaTuner Statistics Server
InstallShield Installation Information
MSECache
```

Aviation / simulator ecosystem folders in `Program Files (x86)` require separate confirmation before any action:

```text
HiFi
FS2Crew*
FSTramp
NavigraphData / Navigraph
Flight Crew A320
Pushback Express MSFS
RAAS Professional
MSFS Map Enhancement
FSrealWX
TOPCAT
```

## Current conclusion

```text
C: cleaned to ~46.12 GiB free
45+ GiB target reached
C: write speed normalized after cleanup
D: pagefile disk is fast
R: MSFS disk is fast
Pagefile 32/64 GB gives strong commit-limit headroom
Further C: cleanup can be postponed
```

## Later possible next steps

If returning to C: cleanup later, use this order:

1. Prefer uninstall flow for large applications; do not manually delete Program Files folders first.
2. Do not touch GIGABYTE or the root utility folders listed above.
3. Check `hiberfil.sys`, shadow storage and `cleanmgr` only separately and with explicit confirmation.
4. Long-term target: keep around `60+ GiB` free on C:.
