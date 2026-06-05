# SPEEDLINK session context — registry recovery, Microsoft driver and vJoy restored

Date: 2026-06-05 late evening / 2026-06-06 early MSK.

This document captures the follow-up session after the `VID_07B5&PID_0317` registry cleanup and reboot. It is intended as recovery context for future work on the SPEEDLINK project.

## Starting point

Before this session:

- The joystick had been unplugged before running registry cleanup.
- `cleanup_device_registry.ps1 -Apply` had deleted 11 matched HKCU keys for `VID_07B5&PID_0317`, with backups written under `C:\SPEEDLINK\NEWVER\registry_backups`.
- The user rebooted Windows, installed drivers, and reconnected the joystick to the selected stable USB port `rear3`.

## Driver outcome

After reboot and reconnect:

- The joystick connected successfully on `rear3`.
- In `joy.cpl`, it did **not** appear as `Speedlink Black Widow`.
- It appeared as `8 button with vibration` / standard Microsoft device behavior.
- Windows `joy.cpl` now exposed calibration and reset controls that were previously unavailable.
- All physical controls worked in `joy.cpl`:
  - X axis
  - Y axis
  - Z axis / throttle / RUD
  - R / twist
  - buttons
  - POV hat

The user found a newer-looking vendor driver named `SL-6640-SBK_Driver_V4.0` from 2013, newer than the earlier official `SL-6640` driver link found during the session. However, the user reported that with `SL-6640-SBK_Driver_V4.0` the X axis had previously jittered.

Decision:

- Do **not** install `SL-6640-SBK_Driver_V4.0` for now.
- Keep the current standard Microsoft HID/DirectInput driver because it is cleaner and more stable for this project.
- Treat the device name `8 button with vibration` / `Microsoft PC-joystick driver` as cosmetic as long as VID/PID and controls are correct.

## JoyDiag verification after recovery

The user verified in `joy_diag.py`:

- Device is found.
- VID/PID is visible as `07B5 / 0317`.
- Live preview shows X/Y/Z/R, buttons and POV.
- X stands still even without Windows OS calibration.

The user attached a fresh `joydiag_profile_final.json` and `joydiag_rest.csv`.

Observed profile metadata:

```json
{
  "device": {
    "name": "Microsoft PC-joystick driver",
    "vid": "0x07B5",
    "pid": "0x0317",
    "joy_id": 0
  },
  "generated": "2026-06-05 23:52:37",
  "vjoy_target": 1
}
```

Observed rest CSV summary:

```text
X mean=-0.000015 spread=0 sigma=0 drift=0
Y mean=-0.000015 spread=0 sigma=0 drift=0
Z mean=-0.000015 spread=0 sigma=0 drift=0
R mean=-0.000015 spread=0 sigma=0 drift=0
U mean=-1.000000 spread=0 sigma=0 drift=0
V mean=-1.000000 spread=0 sigma=0 drift=0
```

Interpretation:

- X/Y/Z/R are effectively perfectly stable at rest.
- No measurable jitter was present in the attached rest CSV.
- Edge calibration worked: X/Y/Z/R had `calibrated_min: -1.0` and `calibrated_max: 1.0` in the profile.
- This confirmed that the earlier edge-calibration symptom was resolved in the recovered environment.

## Z axis / throttle correction

The generated profile classified Z as a `stick` because the throttle happened to be near the center during the rest measurement:

```json
"Z": {
  "type": "stick",
  "center_offset": 1.5259021896696368e-05,
  "deadzone": 0.005,
  "scale_pos": 0.9999847412109375,
  "scale_neg": 1.000015259254738,
  "invert": false,
  "calibrated_min": -1.0,
  "calibrated_max": 1.0
}
```

The user confirmed that Z is the aircraft throttle / RUD axis and is **not** self-centering. Therefore Z must be treated as throttle, not stick.

The corrected Z section is:

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

The assistant prepared and returned two files to the user:

- `joydiag_profile_final.json`
- `vjoy_feeder.py`

The returned profile had Z corrected to `type: "throttle"`. The returned `vjoy_feeder.py` was the current project feeder using VID/PID matching, runtime auto-centering, buttons and POV forwarding.

## vJoyConf issue and fix

Initial feeder run failed:

```text
PS C:\SPEEDLINK\NEWVER> python vjoy_feeder.py
[2026-06-06 00:11:51] profile: C:\SPEEDLINK\NEWVER\joydiag_profile_final.json
ERROR: Could not acquire vJoy #1; it may be busy or disabled
```

Diagnosis:

- The problem was with virtual `vJoy #1`, not with the physical Speedlink joystick.
- Possible causes were: vJoy device busy, disabled, or misconfigured.
- The user suspected that vJoy Device 1 might not be enabled in `vJoyConf`.

`vJoyConf` did not show an option named `1 discrete`; it offered:

- `1 continuous`
- `POV 4 directions`

Decision:

- Select `POV 4 directions`.
- This matches the feeder's use of `SetDiscPov(...)`.
- Configure vJoy Device 1 with:
  - X
  - Y
  - Z
  - Rx
  - Ry
  - Rz
  - at least 8 buttons
  - POV 4 directions

After this vJoyConf change, feeder startup succeeded.

## Successful feeder startup

Successful run:

```text
PS C:\SPEEDLINK\NEWVER> python vjoy_feeder.py
[2026-06-06 00:19:27] profile: C:\SPEEDLINK\NEWVER\joydiag_profile_final.json
[2026-06-06 00:19:27] vJoy #1 acquired via C:\Program Files\vJoy\x64\vJoyInterface.dll
[2026-06-06 00:19:27] physical device: id=0 Microsoft PC-joystick driver VID_07B5&PID_0317
[2026-06-06 00:19:29] auto-center X: -0.0000 spread=0.0000
[2026-06-06 00:19:29] auto-center Y: -0.0000 spread=0.0000
[2026-06-06 00:19:29] auto-center R: -0.0000 spread=0.0000
```

Important interpretation:

- `vJoy #1 acquired` means vJoy Device 1 is now enabled and available.
- Physical joystick was found by VID/PID.
- Auto-centering ran only for X/Y/R.
- Z did **not** auto-center, proving that the corrected `type: "throttle"` profile was loaded.

## Final functional verification in joy.cpl

With `vjoy_feeder.py` running, the user checked `vJoy Device` in `joy.cpl` and confirmed:

- X moves and returns to center.
- Y moves and returns to center.
- R/twist moves and returns to center.
- Z/RUD moves through full travel and stays where left.
- Buttons work.
- POV/hat works in four directions.

The user also noted that R/twist appears in `joy.cpl` as `X Rotation`.

This is expected mapping:

```text
Physical X / roll       -> vJoy X
Physical Y / pitch      -> vJoy Y
Physical Z / throttle   -> vJoy Z
Physical R / twist      -> vJoy Rx -> joy.cpl: X Rotation
```

Expected final axis behavior:

```text
X returns to center      yes
Y returns to center      yes
R / X Rotation centers   yes
Z / RUD stays in place   yes
```

## Final session decision

Final working configuration:

```text
Physical joystick: Microsoft PC-joystick driver / VID_07B5&PID_0317
Physical device name in joy.cpl: 8 button with vibration
USB port: rear3
Driver: standard Microsoft HID/DirectInput
Vendor driver SL-6640-SBK_Driver_V4.0: do not install for now
vJoy target: Device #1
vJoy POV mode: POV 4 directions
Z/RUD: throttle, no auto-center, no deadzone
X/Y/R: stick axes with runtime auto-centering
```

Current status:

- Registry cleanup + reboot succeeded.
- The standard Microsoft driver produced stable axis data.
- JoyDiag sees the device by correct VID/PID.
- Edge calibration works.
- Corrected profile works.
- `vjoy_feeder.py` works.
- vJoy Device 1 receives axes, buttons and POV correctly.

## Next likely step

Only after confirming mappings inside MSFS, consider hiding the physical joystick from MSFS via HidHide so the simulator sees only `vJoy Device`.

Do not change drivers again unless there is a specific reason such as missing force feedback/vibration or broken input mapping. The current Microsoft driver path is cleaner for the correction pipeline.
