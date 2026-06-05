# Session context: Speedlink registry recovery and JoyDiag safety fixes

Date: 2026-06-05 22:00–23:00 MSK  
User: Evgen Kamenskih  
Project: `SPEEDLINK` in `mergelord/practicum`  
Device: Speedlink Black Widow SL-6640, `VID_07B5&PID_0317`

## Why this session happened

During final live testing of the Speedlink workflow, edge calibration in `joy_diag.py` reported that axes were not moved even though the user physically moved all axes.

The user also reported that Windows `joy.cpl` no longer displayed the joystick as `Speedlink Black Widow SL-6640`; it appeared as a generic `USB Game Controller`. The user had installed the vendor driver before, so preserving/restoring vendor identification mattered.

Important facts established during the session:

- `vjoy_feeder.py` was not running.
- vJoy itself was not active for this test.
- `setup_hidhide.ps1` had never been run on this machine.
- In Windows `joy.cpl`, all axes, buttons, and POV worked.
- In `joy_diag.py` raw/live preview, all axes, buttons, and POV also worked.

Conclusion: the physical controller and winmm reading path were alive. The edge-calibration issue was in JoyDiag's calibration/reporting path, and the generic Windows name was likely caused by overly aggressive registry cleanup/reset behavior.

## JoyDiag fixes made

### PR #6 — `Make JoyDiag Windows calibration reset safe`

URL: <https://github.com/mergelord/practicum/pull/6>

Merged: yes.

Changes:

- Removed automatic deletion of registry trees from `joy_diag.py` Windows calibration reset.
- Renamed the UI action to a safe reset flow.
- The reset action now gives instructions to use Windows UI instead of deleting registry branches directly:

```text
joy.cpl → physical controller → Properties → Settings → Reset → reconnect USB
```

- Rationale: deleting the whole `Joystick\OEM\VID_...` branch can also delete OEM/vendor identity data such as display name from the vendor driver.
- Improved edge calibration logging:
  - logs `min`, `max`, and `span` per axis;
  - says whether each axis was saved or skipped;
  - replaces the old misleading generic `(оси не двигали)` message with actionable detail.
- Replaced the previous opaque vJoy-range threshold with:

```python
EDGE_MIN_SPAN = 0.01
```

`joy_core.py` was not changed because calibrated ranges were already applied correctly there; the problem was in `joy_diag.py` UX/registry behavior.

## Registry cleanup tool added and iterated

The user then asked for an automated tool to find and remove all registry keys related to `VID_07B5&PID_0317`, because doing it manually was too tedious.

### PR #7 — `Add guarded registry cleanup tool for Speedlink`

URL: <https://github.com/mergelord/practicum/pull/7>

Merged: yes.

Added:

```text
SPEEDLINK/cleanup_device_registry.ps1
```

Purpose:

- Scan for registry keys/values related to `VID_07B5&PID_0317`.
- Default mode: scan-only, no deletion.
- Deletion requires `-Apply`.
- Backups are written before deletion to:

```text
SPEEDLINK\registry_backups
```

- Low-level `Enum\HID` / `Enum\USB` branches are not touched unless `-IncludeEnum` is explicitly passed.
- Exact full VID/PID matching is used by default. Broad VID-only/PID-only matching is only available with `-BroadMatch`.

### PR #8 — `Fix registry cleanup PowerShell syntax`

URL: <https://github.com/mergelord/practicum/pull/8>

Merged: yes.

Reason:

PowerShell parsed this form incorrectly:

```powershell
"KEY$mark: ..."
```

because `$mark:` is treated as an invalid variable reference.

Fix:

```powershell
Write-Line ("KEY{0}: {1}" -f $mark, $entry.Path)
Write-Line ("VALUE{0}: {1} :: {2} = {3}" -f $mark, $entry.Path, $entry.Name, $entry.Value)
```

### PR #9 — `Avoid reserved PID variable in registry cleanup script`

URL: <https://github.com/mergelord/practicum/pull/9>

Merged: yes.

Reason:

PowerShell has a built-in read-only `$PID` variable. The script parameter:

```powershell
[string]$Pid = "0317"
```

failed with:

```text
Cannot overwrite variable Pid because it is read-only or constant.
```

Fix:

```powershell
[Alias("Pid")]
[string]$ProductId = "0317"
```

Internal uses were changed from `$Pid` to `$ProductId`.

### PR #10 — `Make registry cleanup scan fast by default`

URL: <https://github.com/mergelord/practicum/pull/10>

Merged: yes.

Reason:

The default scan recursively walked these huge branches:

```text
HKCU\Software
HKLM\SOFTWARE
```

On Windows, this looked like a hang.

Fix:

Default scan now only checks targeted joystick/DirectInput branches:

```text
HKCU\...\Joystick
HKLM\...\Joystick
HKCU\...\DirectInput
HKLM\...\DirectInput
```

Deep `Software` scan is now opt-in:

```powershell
-IncludeSoftware
```

Low-level device enum scan remains opt-in:

```powershell
-IncludeEnum
```

## Commands used by the user

After PR #10, the user ran:

```powershell
cd C:\SPEEDLINK\NEWVER
powershell -ExecutionPolicy Bypass -File .\cleanup_device_registry.ps1
```

The scan completed quickly and found 11 keys, all under HKCU user-level joystick/DirectInput paths for `VID_07B5&PID_0317`:

- `HKCU\...\Joystick\OEM\VID_07B5&PID_0317`
- `HKCU\...\DirectInput\VID_07B5&PID_0317`
- `HKCU\...\DirectInput\VID_07B5&PID_0317\Calibration...`
- `HKCU\...\DirectInput\VID_07B5&PID_0317\DeviceInstances`

No matched values were found.

Then the user ran from elevated PowerShell:

```powershell
cd C:\SPEEDLINK\NEWVER
powershell -ExecutionPolicy Bypass -File .\cleanup_device_registry.ps1 -Apply
```

Result:

- `Matched keys: 11`
- `Matched values: 0`
- All matched keys were deleted.
- `.reg` backups were written to:

```text
C:\SPEEDLINK\NEWVER\registry_backups
```

The cleanup ended with:

```text
Done. Reboot Windows, then reinstall vendor driver if needed and reconnect the controller.
```

## Current state at session end

Completed:

- JoyDiag no longer performs dangerous automatic Windows registry deletion.
- Edge calibration now logs detailed min/max/span per axis.
- Registry cleanup tool exists and has been debugged through parser, `$PID`, and slow-scan issues.
- The user successfully ran targeted scan and `-Apply` cleanup.
- HKCU DirectInput/Joystick/OEM records for `VID_07B5&PID_0317` were deleted with backups.

Pending user-side steps:

1. Physically unplug the joystick from USB.
2. Reboot Windows.
3. Reinstall the vendor Speedlink Black Widow SL-6640 driver with the joystick disconnected unless the installer asks otherwise.
4. Reconnect the joystick, preferably to the selected stable port `rear3`.
5. Check `joy.cpl`:
   - whether the vendor name is restored;
   - whether X/Y/Z/R axes move;
   - whether buttons work;
   - whether POV works.
6. Run `python joy_diag.py` and verify raw/live preview.
7. Re-test edge calibration logging if needed.
8. If normal HKCU cleanup does not restore the vendor identity, consider the next level only after confirmation:

```powershell
powershell -ExecutionPolicy Bypass -File .\cleanup_device_registry.ps1 -Apply -IncludeEnum
```

Do not run `-IncludeEnum`, `-IncludeSoftware`, or `-BroadMatch` unless the targeted cleanup is insufficient.

## Port and device notes retained from earlier session

- Preferred port from previous logs: `rear3`.
- Backup port: `rear4`.
- `rear2` was stable in center testing but was not jitter-tested in the provided jitter logs.
- `rear1` was also effectively fine but had a tiny observed center offset around `-0.000015`.

## Important caution for future agents

Do not reintroduce automatic deletion of `Joystick\OEM\VID_...` inside `joy_diag.py`. Registry removal should remain an explicit repair tool with scan-only default, backup, and clear user intent.

For ordinary calibration reset, prefer Windows UI:

```text
joy.cpl → physical controller → Properties → Settings → Reset
```
