# Session context — final MSFS working configuration

Date: 2026-06-07, night MSK.

## Summary

The current Speedlink Black Widow / vJoy / HidHide setup is working correctly in Microsoft Flight Simulator 2020.

User report:

```text
сейчас все работает. мне удалось корректно настроить все оси в MFS 2020.
ничего не дрожит и не уводит сейчас.
днем сделаю еще один тест на пару часов в полете
```

Conclusion: the current configuration should be treated as the latest known-good baseline.

## Current hardware and runtime chain

```text
Physical Speedlink Black Widow SL-6640 / VID_07B5&PID_0317
-> hidden from MSFS by HidHide
-> visible to Python/pythonw through HidHide whitelist
-> vjoy_feeder.py reads the physical joystick through winmm
-> vJoy Device #1 receives corrected axes/buttons/POV
-> MSFS 2020 sees and uses vJoy Device
```

Current physical device names observed during the recovery work:

```text
Windows/joy.cpl before hiding: 8 button with vibration
JoyDiag/winmm: Microsoft PC-joystick driver
HidHide: Mega World USB Game Controllers
```

Preferred USB port remains:

```text
rear3
```

## Final axis routing after rollback

The previous experiment that copied physical X into vJoy Rx for nose-wheel steering caused unwanted steering pull in MSFS/Fenix. That experiment has been rolled back.

Current profile routing:

```json
"output_map": {
  "X": ["X"],
  "Y": ["Y"],
  "Z": ["Z"],
  "R": [],
  "U": [],
  "V": []
}
```

Meaning:

```text
physical X        -> vJoy X only
physical Y        -> vJoy Y
physical Z / RUD  -> vJoy Z
physical R/twist  -> disabled / not sent
vJoy Rx/Ry/Rz     -> centered / unused
```

Important: physical X is no longer copied into vJoy Rx.

## MSFS 2020 state

The user reports that all axes were configured correctly in MSFS 2020 and that the sim currently has:

```text
no jitter
no axis drift
no unwanted steering pull
```

This means the working MSFS control profile should not be disturbed unless a new issue appears.

## Nose wheel / steering lesson learned

The X -> Rx routing experiment made nose-wheel steering work, but it also made steering pull left/right.

Likely reason:

```text
Nose Wheel Steering / Tiller is very sensitive to small residual center offsets.
When physical X was copied to vJoy Rx, any tiny X offset became a steering command.
```

Therefore the final working setup avoids using vJoy Rx for nose-wheel steering.

If steering pull returns, first check that MSFS/Fenix no longer has old bindings like:

```text
Nose Wheel Steering Axis = vJoy Rx
Tiller Axis              = vJoy Rx
```

and verify in `joy.cpl -> vJoy Device` that:

```text
vJoy Rx / X Rotation stays centered
physical X does not move vJoy Rx
```

## Z / throttle anti-jitter state

The Z/RUD axis remains a throttle-style axis and keeps the hold filter:

```json
"Z": {
  "type": "throttle",
  "center_offset": 0.0,
  "deadzone": 0.0,
  "scale_pos": 1.0,
  "scale_neg": 1.0,
  "invert": false,
  "hold_threshold": 0.03
}
```

This is still considered successful based on the earlier 1.5-hour MSFS test and the current user report that nothing jitters.

## Current expected joy.cpl behavior

In `joy.cpl -> vJoy Device`:

```text
X moves from physical X
Y moves from physical Y
Z/RUD moves through the full throttle range and stays where left
Rx / X Rotation stays centered and is not driven by physical X or physical twist
buttons work
POV/hat works
```

## Current operational commands

Restart feeder after copying updated files:

```powershell
cd C:\SPEEDLINK\NEWVER
Stop-ScheduledTask -TaskName vJoyFeeder
Start-ScheduledTask -TaskName vJoyFeeder
```

Run control GUI:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\feeder_gui.py
```

Manual pause:

```powershell
New-Item -ItemType File -Path C:\SPEEDLINK\NEWVER\vjoy_feeder.pause -Force
```

Manual resume:

```powershell
Remove-Item C:\SPEEDLINK\NEWVER\vjoy_feeder.pause -ErrorAction SilentlyContinue
```

## Next planned validation

The user plans a longer daytime test flight of roughly a couple of hours.

During that test, watch only for:

```text
1. X/Y drift or unwanted roll/pitch behavior;
2. Z/RUD jitter in intermediate throttle positions;
3. old nose-wheel/tiller pull returning after MSFS restart or profile reload.
```

If the longer flight remains clean, this setup should be considered the final stable baseline for this Speedlink Black Widow / MSFS 2020 configuration.

## Related PRs / changes

Most relevant recent changes:

```text
PR #16 — Add throttle hold filter for noisy Z axis
PR #19 — Add feeder GUI and output mapping support
PR #20 — Remove Speedlink X nose wheel routing
```

The current stable behavior depends on PR #20's rollback of X -> Rx routing while keeping the safer `output_map` mechanism available for future use.
