# Session context — 2026-06-08 — SSD free space cleanup and TRIM verification

Date: 2026-06-08, day MSK.
Status: C: system disk reached the long-term `60+ GiB` free-space target; TRIM/retrim was verified on `C:`, `D:`, `R:`, `Z:` and `K:`.

## Summary

This session continued the conservative Windows/system SSD cleanup after the earlier system disk cleanup session.

The key constraints remained:

- `C:\Users\MYRIG` is the user's production Windows profile.
- Do not delete broad profile folders such as `AppData`, `Local`, `Roaming`, `Packages`, browser profiles, tokens, aviation/sim data, or program settings.
- Only remove targeted caches, old application versions, leftovers from already-uninstalled software, or packages the user explicitly confirmed are no longer needed.

Final result for `C:`:

```text
FreeSpace=64474406912
Size=255257083904
≈60.05 GiB free
≈64.47 GB free
```

After retrim, Windows reported:

```text
Volume size = 237.72 GB
Used space  = 177.69 GB
Free space  = 60.03 GB
```

The `60+ GiB` free-space target was reached.

## C: cleanup performed in this part of the session

The previous known free-space point before this continuation was after OmniRoute folder removal:

```text
FreeSpace=58255568896 bytes
≈54.25 GiB
```

Targeted cleanup actions:

- Removed `C:\Users\MYRIG\.omniroute` after confirming no OmniRoute process was running.
- Uninstalled global npm package `omniroute` through npm:

```cmd
npm uninstall -g omniroute
```

Result:

```text
removed 904 packages in 5s
```

Follow-up checks confirmed both were gone:

```text
C:\Users\MYRIG\AppData\Roaming\npm\node_modules\omniroute -> File Not Found
C:\Users\MYRIG\AppData\Roaming\npm\omniroute* -> File Not Found
```

- Removed MathWorks/MATLAB leftovers after the official Windows uninstaller finished. Active leftovers were first stopped:

```text
MathWorksServiceHost
MathWorksServiceHost-Monitor
```

Then targeted paths were removed only for MathWorks/MATLAB/Polyspace:

```text
C:\Users\MYRIG\AppData\Local\MathWorks
C:\Users\MYRIG\AppData\Roaming\MathWorks
C:\Users\MYRIG\AppData\LocalLow\MathWorks
C:\ProgramData\MathWorks
C:\Program Files\MATLAB
C:\Program Files\Polyspace
C:\Program Files (x86)\MATLAB
C:\Program Files (x86)\Polyspace
```

MathWorks cleanup increased free space by about `2.22 GiB`.

- Removed Arena Breakout Infinite CDN cache:

```text
C:\Users\MYRIG\AppData\Local\ABInfinite\Saved\CDNCached\en
```

This was handled safely:

1. Rename `en` to `en_BACKUP_DELETE_LATER`.
2. Launch Arena Breakout Infinite from `R:\Arena Breakout Infinite\`.
3. Confirm the game starts and works normally.
4. Delete the backup folder.

Freed about `474 MiB`.

- Removed old Discord application versions from:

```text
C:\Users\MYRIG\AppData\Local\Discord\
```

Detected versions:

```text
app-1.0.9240  0.371 GiB  2026-06-04  -> kept, current
app-1.0.9031  0 GiB      2024-06-12  -> kept as harmless fallback
app-0.0.306   0.122 GiB  2020        -> removed
app-0.0.308   0.130 GiB  2020        -> removed
app-0.0.309   0.136 GiB  2020        -> removed
```

Discord was launched successfully after renaming old versions, then the backup folders were deleted. Freed about `352 MiB`.

- The user additionally cleaned old versions in:

```text
C:\Users\MYRIG\AppData\Roaming\JetBrains\
```

This freed about `1.51 GiB` and pushed `C:` over `60 GiB` free.

## Free-space milestones

Important checkpoints:

```text
After final AOMEI/Epic/Hotspot cleanup:
FreeSpace=49515089920
≈46.12 GiB

After deleting C:\Users\MYRIG\.omniroute:
FreeSpace=58255568896
≈54.25 GiB

After MathWorks/MATLAB leftovers:
FreeSpace=60642480128
≈56.48 GiB

After ABInfinite CDN cache:
FreeSpace=61139578880
≈56.93 GiB

After old Discord app folders:
FreeSpace=61508460544
≈57.28 GiB

After npm global omniroute uninstall:
FreeSpace=62857875456
≈58.55 GiB

After old JetBrains versions:
FreeSpace=64474406912
≈60.05 GiB
```

Goal status:

```text
45+ GiB: done
50+ GiB: done
60 decimal GB: done
60 GiB: done
```

## Repeat C: CrystalDiskMark result

After more free space was available, C: was retested:

```text
Date: 2026/06/08 13:56:15
Profile: Peak
Test: 1 GiB x3
C: 79% used, 189/238 GiB
Mode: Admin

SEQ 1MiB Q8T1 Read: 2992.461 MB/s
SEQ 1MiB Q8T1 Write: 2733.666 MB/s
RND 4KiB Q32T16 Read: 1886.908 MB/s / 460670.9 IOPS
RND 4KiB Q32T16 Write: 1371.861 MB/s / 334927.0 IOPS
```

Conclusion: the earlier C: sequential write collapse to about `74 MB/s` was likely temporary and related to high fill level, SLC/cache/background activity, or write pressure. It is not evidence of confirmed SSD failure.

## Free-space guidance for C:

For the system SSD:

```text
<10% free      -> bad for SSD and Windows
10-15% free    -> borderline
15-20% free    -> normal
20-25% free    -> good
25%+ free      -> excellent
```

For this specific `C:` volume:

```text
red zone:       below 25 GiB
undesirable:    below 35 GiB
normal:         40-50 GiB
good:           50-60 GiB
excellent:      60+ GiB
```

Current state is excellent: around `60 GiB` free, roughly `25%` of the volume.

## TRIM / DisableDeleteNotify check

Command:

```cmd
fsutil behavior query DisableDeleteNotify
```

Result:

```text
NTFS DisableDeleteNotify = 0  (Disabled)
ReFS DisableDeleteNotify = 0  (Disabled)
```

Interpretation: the setting name is `DisableDeleteNotify`; value `0` means disabling TRIM is disabled, therefore TRIM is enabled.

## Retrim result for C:

Command:

```cmd
defrag C: /L /V
```

Result:

```text
Invoking retrim on (C:)...
The operation completed successfully.

Volume Information:
Volume size                 = 237.72 GB
Cluster size                = 4 KB
Used space                  = 177.69 GB
Free space                  = 60.03 GB

Retrim:
Backed allocations          = 238
Allocations trimmed         = 16835
Total space trimmed         = 57.68 GB
```

Conclusion: TRIM/retrim works correctly on the system SSD `C:`.

## Free space and retrim for D/R/Z/K

The user checked free space and ran retrim on all other SSD volumes.

Commands:

```cmd
wmic logicaldisk where "DeviceID='D:'" get Size,FreeSpace /Value
wmic logicaldisk where "DeviceID='R:'" get Size,FreeSpace /Value
wmic logicaldisk where "DeviceID='Z:'" get Size,FreeSpace /Value
wmic logicaldisk where "DeviceID='K:'" get Size,FreeSpace /Value

defrag D: /L /V
defrag R: /L /V
defrag Z: /L /V
defrag K: /L /V
```

### D: pagefile disk

```text
FreeSpace=149817376768
Size=1024208138240

Volume size                 = 953.86 GB
Used space                  = 814.33 GB
Free space                  = 139.52 GB

Retrim:
Backed allocations          = 954
Allocations trimmed         = 286
Total space trimmed         = 139.50 GB
```

Assessment: TRIM succeeded. Free space is about `14.6%`, which is normal but near the lower comfort boundary. Because `D:` hosts `D:\pagefile.sys`, preferred target is `150-200+ GiB` free.

### R: MSFS disk

```text
FreeSpace=576919056384
Size=2048405794816

Volume size                 = 1.86 TB
Used space                  = 1.33 TB
Free space                  = 537.29 GB

Retrim:
Backed allocations          = 1908
Allocations trimmed         = 3411
Total space trimmed         = 537.05 GB
```

Assessment: TRIM succeeded. Free space is about `28.1%`, excellent for the MSFS disk.

### Z:

```text
FreeSpace=129477283840
Size=900182568960

Volume size                 = 838.35 GB
Used space                  = 717.77 GB
Free space                  = 120.58 GB

Retrim:
Backed allocations          = 839
Allocations trimmed         = 1541
Total space trimmed         = 120.59 GB
```

Assessment: TRIM succeeded. Free space is about `14.4%`, normal but near the lower comfort boundary. Preferred target is `130-170+ GiB` free.

### K:

```text
FreeSpace=115997876224
Size=128033222656

Volume size                 = 119.23 GB
Used space                  = 11.20 GB
Free space                  = 108.03 GB

Retrim:
Backed allocations          = 120
Allocations trimmed         = 124
Total space trimmed         = 108.04 GB
```

Assessment: TRIM succeeded. Free space is about `90.6%`, excellent.

## SSD free-space recommendations

General rule:

```text
<10% free       -> bad / red zone
10-15% free     -> minimum acceptable
15-20% free     -> normal
20-25% free     -> good
25%+ free       -> excellent
```

Practical targets for this machine:

```text
C:  keep 50-60+ GiB free; current state is excellent
D:  keep 150-200+ GiB free because it hosts pagefile
R:  keep 300-500+ GiB free; current state is excellent
Z:  keep 130-170+ GiB free
K:  keep 20-30+ GiB free; current state is excellent
```

Red lines:

```text
D: below ~100 GiB -> avoid
R: below ~200 GiB -> avoid
Z: below ~80-100 GiB -> avoid
K: below ~12-15 GiB -> avoid
```

## Final status

```text
C: excellent, ~60 GiB free
D: normal, but preferably free another 10-60 GiB later
R: excellent
Z: normal, but preferably free another 10-50 GiB later
K: excellent
TRIM enabled: yes
Retrim successful: C, D, R, Z, K
C: write speed normalized after cleanup
```

No urgent SSD maintenance issue remains. Future cleanup, if needed, should focus conservatively on `D:` and `Z:` only, not on `R:` or `K:`.

## Do not forget

Do not broadly clean the production profile `C:\Users\MYRIG`. Continue to avoid:

- browser profiles and tokens;
- `AppData\Local\Packages`;
- whole `AppData`, `Local`, `Roaming`, `Program Files`, or `ProgramData` trees;
- aviation/sim folders unless the user explicitly confirms;
- `GIGABYTE` folders unless explicitly confirmed;
- root tool folders previously marked as do-not-touch.
