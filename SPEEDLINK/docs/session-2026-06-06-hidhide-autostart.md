# SPEEDLINK session context — autostart, deadzones and HidHide

Date: 2026-06-06 early MSK.

This document captures the final stabilization session after restoring the Speedlink Black Widow / SL-6640 pipeline through the Microsoft HID driver, JoyDiag, vJoy and HidHide.

## Confirmed working base before this session

- Physical joystick is connected to USB port `rear3`.
- Windows identifies it through the standard Microsoft HID/DirectInput path, not the older Speedlink V4.0 driver.
- The physical device may appear under different names depending on the tool:
  - `8 button with vibration` in `joy.cpl`.
  - `Microsoft PC-joystick driver` in JoyDiag / winmm.
  - `Mega World USB Game Controllers` in HidHide.
- VID/PID remains correct: `VID_07B5&PID_0317`.
- The Speedlink V4.0 driver is **not** recommended for the current setup because it previously made X drift/jitter, while the Microsoft driver gives a cleaner base signal.

## Profile and deadzone tuning

The user confirmed that Z is the aircraft throttle / RUD axis and does not return to center. The profile must therefore treat Z as `throttle`, not `stick`.

Final working profile policy:

```text
X: stick, deadzone 0.010
Y: stick, deadzone 0.015
R: stick/twist, deadzone 0.010
Z: throttle/RUD, deadzone 0.000, no center offset, no auto-center
```

Z section:

```json
"Z": {
  "type": "throttle",
  "center_offset": 0.0,
  "deadzone": 0.0,
  "scale_pos": 1.0,
  "scale_neg": 1.0,
  "invert": false,
  "calibrated_min": -1.0,
  "calibrated_max": 1.0
}
```

Reasoning:

- Physical RAW Y reacts to small desk/mouse vibrations.
- After moving and releasing the stick, Y may settle after a few seconds.
- `Reset calibration` in Windows did not change this behavior, so Windows calibration is not the root cause.
- This is likely mechanical sensitivity / spring settling / table vibration, not a driver or registry problem.
- The goal is not to make physical RAW perfectly static; the goal is to make the vJoy output stable.

The assistant generated updated `joydiag_profile_final.json` for the user with:

```text
X deadzone = 0.010
Y deadzone = 0.015
R deadzone = 0.010
Z deadzone = 0.000
```

The user later confirmed in `joy.cpl -> vJoy Device` that all axes were centered and stable.

## vJoyConf configuration

vJoy Device #1 must be enabled in vJoyConf.

Working vJoyConf setup:

```text
Device: 1
Axes: X, Y, Z, Rx, Ry, Rz
Buttons: at least 8
POV: POV 4 directions
```

The local vJoyConf did not offer `1 discrete`; it offered:

```text
1 continuous
POV 4 directions
```

The correct choice for the current feeder is `POV 4 directions`, because `vjoy_feeder.py` uses `SetDiscPov(...)`.

## vJoy feeder autostart

The user installed scheduled-task autostart via elevated PowerShell:

```powershell
cd C:\SPEEDLINK\NEWVER
powershell -ExecutionPolicy Bypass -File .\setup_autostart.ps1 -RunNow
```

First non-elevated attempt failed with:

```text
Register-ScheduledTask : Access is denied.
HRESULT 0x80070005
```

Running from PowerShell as Administrator succeeded:

```text
Registered scheduled task: vJoyFeeder
Script: C:\SPEEDLINK\NEWVER\vjoy_feeder.py
Python: C:\Python314\pythonw.exe
Started scheduled task: vJoyFeeder
```

The scheduled task uses:

```text
C:\Python314\pythonw.exe
```

This matters for HidHide: `pythonw.exe` must be in the HidHide application whitelist.

Observed successful feeder log:

```text
profile: C:\SPEEDLINK\NEWVER\joydiag_profile_final.json
vJoy #1 acquired via C:\Program Files\vJoy\x64\vJoyInterface.dll
physical device: id=0 Microsoft PC-joystick driver VID_07B5&PID_0317
auto-center X: -0.0000 spread=0.0000
auto-center Y: rejected mean=+0.0517 spread=0.0635
auto-center R: -0.0000 spread=0.0000
```

`auto-center Y: rejected` is acceptable: it means the feeder refused to use an unstable Y sample as a runtime center. The user verified afterwards that `joy.cpl -> vJoy Device` had all axes strictly centered and stable.

## HidHide CLI issue and GUI fallback

The project script `setup_hidhide.ps1` initially had a PowerShell parser issue similar to the earlier `$mark:` bug:

```powershell
Write-Host "DevicePath was not provided. Devices containing $VidPid:"
```

This fails because PowerShell parses `$VidPid:` as an invalid variable reference. A PR was opened to replace this with safe formatting:

```powershell
Write-Host ("DevicePath was not provided. Devices containing {0}:" -f $VidPid)
```

However, on the user's machine, HidHideCLI still did not list devices:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_hidhide.ps1 -List
```

Output was only:

```text
HidHideCLI: C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe
```

Therefore final HidHide setup was done through **HidHide Configuration Client** GUI instead of CLI.

## HidHide GUI final setup

Applications whitelist:

```text
C:\Python314\python.exe
C:\Python314\pythonw.exe
```

Important:

- `pythonw.exe` is required because the scheduled task uses `C:\Python314\pythonw.exe`.
- Do **not** add MSFS to the application whitelist, otherwise MSFS will still see the hidden physical joystick.

Devices tab:

- Hide `Mega World USB Game Controllers`.
- Do **not** hide `vJoy`.

`Mega World USB Game Controllers` is the physical Speedlink device as seen by HidHide. It corresponds to the same device that appears elsewhere as:

```text
8 button with vibration
Microsoft PC-joystick driver
VID_07B5&PID_0317
```

Enable:

```text
Enable Device Hiding
```

## Final verification

After enabling HidHide:

- Physical `8 button with vibration` / `Mega World USB Game Controllers` disappeared from `joy.cpl`.
- `vJoy Device` remained visible.
- In `vJoy Device`, all axes and buttons worked.

Final working input chain:

```text
Physical Speedlink Black Widow / VID_07B5&PID_0317
-> hidden from normal apps by HidHide
-> still visible to C:\Python314\pythonw.exe via HidHide whitelist
-> vjoy_feeder.py reads physical joystick through winmm
-> vJoy Device #1 receives corrected axes/buttons/POV
-> MSFS should see only vJoy Device, avoiding duplicate bindings
```

## Final working configuration

```text
USB port: rear3
Driver: standard Microsoft HID/DirectInput
Physical name in joy.cpl before hiding: 8 button with vibration
Physical name in HidHide: Mega World USB Game Controllers
VID/PID: VID_07B5&PID_0317
vJoy target: Device #1
vJoy POV mode: POV 4 directions
Autostart: Scheduled Task vJoyFeeder
Autostart Python: C:\Python314\pythonw.exe
HidHide whitelist: C:\Python314\python.exe and C:\Python314\pythonw.exe
Hidden device: Mega World USB Game Controllers
Do not hide: vJoy Device
```

## Current status

The SPEEDLINK pipeline is operational:

- Registry cleanup and reboot completed.
- Microsoft driver is stable enough and preferred over Speedlink V4.0.
- Profile deadzones are tuned for the real desk/mechanical vibration.
- vJoy Device #1 works.
- vJoy feeder autostart is installed and starts successfully.
- HidHide hides the physical joystick while vJoy remains available.

## Caution for future work

- Do not reinstall `SL-6640-SBK_Driver_V4.0` unless there is a specific need, because it previously caused X drift/jitter.
- Do not hide `vJoy` in HidHide.
- Do not add MSFS to HidHide Applications.
- Keep `C:\Python314\pythonw.exe` whitelisted; otherwise autostarted `vjoy_feeder.py` may lose access to the physical joystick.
- If HidHideCLI does not list devices, use HidHide Configuration Client GUI.
