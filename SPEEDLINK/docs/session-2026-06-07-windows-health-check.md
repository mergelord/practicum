# Session context — Windows health check after MSFS/vJoy stabilization

Date: 2026-06-07, night MSK.

## Summary

After the Speedlink Black Widow / vJoy / HidHide configuration became stable in MSFS 2020, a general Windows health check was performed because earlier logs showed MSFS crashes, Resource Exhaustion warnings, disk paging warnings, and one unexpected reboot.

Main conclusion:

```text
Windows system files and component store are healthy.
The main real issue found in logs was disabled pagefile / low commit limit.
Pagefile has now been enabled, commit limit is healthy, and disk/filesystem checks are clean.
```

This should be treated as the latest system-health context for the Speedlink/MSFS setup.

## Logs reviewed

The following exported health logs were reviewed:

```text
system_errors_warnings.csv
application_errors_warnings.csv
system_filtered_hardware_power_driver.csv
application_filtered_crashes_installs.csv
reliability_records.csv
pnp_problem_devices.csv
```

Important observations from the logs:

```text
Resource-Exhaustion-Detector ID 2004: low virtual memory condition
Windows Error Reporting: paging file is too small for this operation to complete
volmgr ID 46: Crash dump initialization failed
disk ID 51: paging operation warnings on Harddisk0/DR0
Kernel-Power ID 41 / EventLog ID 6008: one unexpected reboot
FlightSimulator.exe crashes in Reliability Monitor
nvlddmkm NVIDIA driver errors
TPM ID 15 warnings
Kernel-PnP WudfRd 219 warnings
many DistributedCOM 10010/10016 events
```

## Low virtual memory / pagefile finding

The important finding was that pagefile was disabled in Windows settings.

This explained the earlier log pattern:

```text
low virtual memory condition
paging file is too small
Windows Error Reporting failure
crash dump initialization failed
MSFS crashes under load
```

Even with 64 GB RAM, Windows still needs a pagefile for commit limit, crash dumps, error reporting, and heavy workloads like MSFS + browser + SimBridge/companion apps.

Pagefile was then enabled.

Verification:

```powershell
wmic pagefile list /format:list
```

Result:

```text
AllocatedBaseSize=16384
CurrentUsage=0
Description=D:\pagefile.sys
Name=D:\pagefile.sys
PeakUsage=0
TempPageFile=FALSE
```

Meaning:

```text
D:\pagefile.sys exists
size: 16 GB
it is permanent, not temporary
```

Commit limit check:

```powershell
Get-Counter '\Memory\Committed Bytes','\Memory\Commit Limit'
```

Result:

```text
Committed Bytes: 35,351,347,200 bytes ≈ 32.9 GB
Commit Limit:    85,713,756,160 bytes ≈ 79.8 GB
```

Conclusion:

```text
Current committed memory: ~33 GB
Current commit limit: ~80 GB
Headroom: ~47 GB
```

This is now healthy enough for the next MSFS test.

## Disk and filesystem checks

`chkdsk C: /scan` was run.

Result:

```text
Windows has scanned the file system and found no problems.
No further action is required.
0 KB in bad sectors.
```

Conclusion:

```text
C: NTFS structure is clean.
No filesystem repair is needed.
```

`Get-PhysicalDisk` showed all listed disks as:

```text
OperationalStatus = OK
HealthStatus      = Healthy
```

Disks listed included:

```text
KINGSTON SKC3000D2048G
WDC WD1002FAEX-00Y9A0
DGSM4001TM63T
WDC WD10EAVS-00M4B0
Samsung SSD 980 1TB
TOSHIBA THNSNH128GBST
ST3500413AS
Colorful CN600 256GB PRO
```

Conclusion:

```text
Windows does not report an active disk-health failure.
The earlier disk ID 51 warnings are now more likely related to the disabled pagefile / paging pressure / abrupt shutdown context than an immediately obvious filesystem failure.
```

CrystalDiskInfo/SMART can still be used later for deeper disk confidence, but current Windows checks are clean.

## SFC / DISM / component store checks

The motherboard BIOS was reported to already be on the latest version.

SFC:

```powershell
sfc /scannow
```

Result:

```text
Windows Resource Protection did not find any integrity violations.
```

DISM CheckHealth:

```powershell
DISM /Online /Cleanup-Image /CheckHealth
```

Result:

```text
No component store corruption detected.
The operation completed successfully.
```

DISM ScanHealth:

```powershell
DISM /Online /Cleanup-Image /ScanHealth
```

Result:

```text
No component store corruption detected.
The operation completed successfully.
```

DISM AnalyzeComponentStore:

```powershell
DISM /Online /Cleanup-Image /AnalyzeComponentStore
```

Result:

```text
Windows Explorer Reported Size of Component Store : 5.15 GB
Actual Size of Component Store : 5.11 GB
Shared with Windows : 2.77 GB
Backups and Disabled Features : 1.95 GB
Cache and Temporary Data : 378.38 MB
Date of Last Cleanup : 2026-06-01 19:43:02
Number of Reclaimable Packages : 0
Component Store Cleanup Recommended : No
```

Conclusion:

```text
Windows system files are healthy.
Component Store / WinSxS is healthy.
DISM RestoreHealth is not needed.
DISM StartComponentCleanup is not needed.
```

## Remaining non-critical observations

The following remain observation-only unless symptoms return:

```text
nvlddmkm NVIDIA errors
TPM ID 15 warnings
Kernel-PnP WudfRd 219 warnings
DistributedCOM 10010/10016 noise
GIGABYTE Control Center / GbtCloudMatrix crashes
Happ.exe crash
NetBT / duplicate computer name errors
```

Priority notes:

```text
DistributedCOM 10010/10016: ignore unless a concrete app symptom appears.
NETLOGON 3095: expected/noisy on a workgroup PC.
TPM ID 15: do not touch unless BitLocker/Windows Hello/TPM symptoms appear.
WudfRd 219: low priority; may improve with chipset/Intel drivers later.
GIGABYTE utilities: can be disabled from startup if not needed.
NVIDIA: only investigate/clean-install driver if MSFS or GPU symptoms continue after pagefile fix.
```

## Current system-health baseline

Current known state:

```text
BIOS: latest version
SFC: clean
DISM CheckHealth: clean
DISM ScanHealth: clean
DISM AnalyzeComponentStore: cleanup not recommended
CHKDSK C: clean
PhysicalDisk: all Healthy
Pagefile: enabled, D:\pagefile.sys, 16 GB
Commit limit: ~80 GB
Speedlink/vJoy/MSFS: currently working with no jitter, no drift, no steering pull
```

## Recommendation for next MSFS test

Before the daytime 2+ hour MSFS test:

```text
1. Reboot Windows after pagefile change.
2. Confirm pagefile persists:
   wmic pagefile list /format:list
3. Start the Speedlink/vJoy/HidHide chain normally.
4. Keep unnecessary browsers/overlays closed.
5. Fly for 2+ hours.
```

Watch for:

```text
MSFS crash
Resource-Exhaustion warnings
Windows Error Reporting pagefile errors
disk ID 51 returning
Kernel-Power 41 / unexpected reboot
Z/RUD jitter
X/Y drift
nose steering pull
```

If the test is clean, the current Windows + Speedlink/vJoy/MSFS configuration should be considered stable.
