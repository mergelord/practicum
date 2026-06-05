# SPEEDLINK session context — Z/RUD throttle noise follow-up

Date: 2026-06-06 early MSK.

This note captures the follow-up after the Speedlink Black Widow / SL-6640 pipeline was already restored with:

- Microsoft HID/DirectInput driver.
- `vjoy_feeder.py` autostart through Scheduled Task `vJoyFeeder`.
- HidHide hiding the physical device from MSFS.
- vJoy Device #1 visible and working in MSFS.

## Starting state

The working chain before this follow-up was:

```text
Physical Speedlink Black Widow / VID_07B5&PID_0317
-> hidden by HidHide
-> still visible to C:\Python314\pythonw.exe
-> vjoy_feeder.py reads it through winmm
-> vJoy Device #1 receives corrected axes/buttons/POV
-> MSFS sees vJoy Device only
```

Confirmed earlier:

- Physical device was hidden from `joy.cpl` as `8 button with vibration` / `Mega World USB Game Controllers`.
- `vJoy Device` remained visible.
- vJoy axes and buttons worked.
- MSFS 2020 worked through vJoy without duplicate physical joystick input.

## New issue found in MSFS 2020

During MSFS 2020 testing, the user reported:

- Everything generally works.
- Z/RUD throttle axis drifts/jitters when it is not in the top or bottom mechanical stop.
- Z is stable only in extreme upper/lower stop positions.
- This is a problem because thrust and reverse are bound to the same axis.

Interpretation:

- Z/RUD is currently configured correctly as `type: "throttle"`, with no center deadzone and no auto-centering.
- Because of that, `vjoy_feeder.py` forwards Z changes 1:1 to vJoy.
- If the physical throttle potentiometer jitters in intermediate positions, MSFS receives that jitter as real thrust/reverse movement.

Likely cause:

```text
Z/RUD potentiometer or mechanical lever is stable in hard stops,
but noisy in intermediate positions.
```

## Proposed fix direction

Do **not** use normal stick-style center deadzone for Z.

Reason:

- Z is not a self-centering axis.
- Thrust/reverse use the whole axis range.
- A center deadzone only solves noise around one point and can distort throttle/reverse behavior.

Better solution for Z/RUD:

```text
Add throttle hold / anti-jitter filtering.
```

Concept:

```text
If the new Z value differs from the last sent Z value by less than a threshold,
keep the previous vJoy Z value.
If the difference is larger than the threshold,
accept and send the new Z value.
```

Possible profile field names discussed:

```json
"hold_threshold": 0.015
```

or:

```json
"jitter_deadband": 0.015
```

Recommended initial range after measuring:

```text
0.010 -> mild hold
0.015 -> likely starting point
0.020+ -> only if measured p2p_Z requires it
```

## Measurement plan before coding

The user correctly asked to measure the physical Z/RUD noise in realistic MSFS throttle positions before implementing a filter.

Because the important positions are aircraft-specific, the planned measurements are:

```text
rear3_idle_reverse -> current IDLE / reverse boundary in MSFS
rear3_z50          -> CLB / Climb position
rear3_z75          -> FLEX position
```

These are more useful than abstract 25/50/75 positions because they correspond to actual MSFS operating points.

## Important measurement caveat

At first, the feeder was stopped for JoyDiag measurement while HidHide still hid the physical joystick. That made MSFS lose joystick input, which is expected:

```text
physical joystick hidden by HidHide
+ vjoy_feeder stopped
= vJoy receives no signal
= MSFS has no working joystick input
```

The user pointed out that the RUD positions must be set in MSFS on real hardware.

Therefore the correct measurement mode for later is:

```text
HidHide OFF
vjoy_feeder OFF
MSFS sees the physical joystick
use MSFS to set IDLE / CLB / FLEX positions
JoyDiag measures the physical joystick
```

After measurements:

```text
HidHide ON
vjoy_feeder ON
MSFS sees only vJoy again
```

## Exact later procedure

When resuming:

1. Temporarily disable HidHide hiding:

```text
HidHide Configuration Client -> Enable Device Hiding = OFF
```

or, if CLI works for this action:

```powershell
cd C:\SPEEDLINK\NEWVER
powershell -ExecutionPolicy Bypass -File .\setup_hidhide.ps1 -Off
```

2. Keep feeder stopped:

```powershell
cd C:\SPEEDLINK\NEWVER
Stop-ScheduledTask -TaskName vJoyFeeder
```

3. Start/open MSFS 2020 and use the physical joystick/RUD to place the throttle at the target detent/position.

4. In JoyDiag, select the physical joystick:

```text
Microsoft PC-joystick driver / VID_07B5&PID_0317
```

5. For each position, run a 60-second jitter measurement with these labels:

```text
rear3_idle_reverse
rear3_z50
rear3_z75
```

6. Send/upload:

```text
port_jitter_log.csv
port_jitter_log_summary.txt, if generated
```

7. Analyze especially:

```text
center_Z
sigma_Z
p2p_Z
drift_Z
```

8. Choose Z hold threshold from measured `p2p_Z`.

9. Implement `vjoy_feeder.py` Z anti-jitter hold filter and update `joydiag_profile_final.json`.

10. Restore operational mode:

```text
HidHide Configuration Client -> Enable Device Hiding = ON
Start-ScheduledTask -TaskName vJoyFeeder
```

## Current stopping point

The user is going to sleep. The Z/RUD measurements and filter implementation are intentionally postponed.

Do not forget the key point when resuming:

```text
For MSFS-referenced throttle detent measurements, HidHide must be temporarily OFF and the feeder OFF, so MSFS can see the physical joystick and the user can place Z/RUD in the real IDLE / CLB / FLEX positions.
```
