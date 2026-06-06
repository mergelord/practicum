# Z/RUD throttle hold filter

Date: 2026-06-06.

## Why this exists

Fresh JoyDiag measurements showed that the Speedlink Black Widow Z/RUD axis jitters even when MSFS is not running. That confirms the root cause is the physical throttle axis / potentiometer / mechanics, not MSFS, vJoy, HidHide, or the Microsoft driver.

Recent measured Z jitter examples on `rear3`:

| Label | center_Z | sigma_Z | p2p_Z | drift_Z |
| --- | ---: | ---: | ---: | ---: |
| `rear3_z25` | `+0.595218` | `0.001844` | `0.015869` | `-0.000225` |
| `rear3_z40` | `+0.348662` | `0.002046` | `0.023804` | `+0.000079` |
| `rear3_z50` | `-0.000605` | `0.002064` | `0.007813` | `-0.000182` |
| `rear3_z60` | `-0.390671` | `0.000439` | `0.007813` | `+0.000039` |
| `rear3_z75` | `-0.580104` | `0.003402` | `0.007813` | `+0.000742` |

Earlier `idle_reverse`-area measurements reached about `p2p_Z = 0.031769`.

## Why normal deadzone is not used

Z/RUD is a throttle axis, not a self-centering stick axis. A normal center deadzone would only suppress noise around one point and would distort throttle/reverse behavior across the axis.

## Implemented behavior

`vjoy_feeder.py` now supports per-axis hold filtering through the profile:

```json
"Z": {
  "type": "throttle",
  "hold_threshold": 0.03
}
```

`jitter_deadband` is also accepted as an alias for `hold_threshold`.

The filter works in normalized `[-1..1]` axis units after the usual profile correction:

```text
if abs(new_value - last_sent_value) < hold_threshold:
    send last_sent_value again
else:
    accept and send new_value
```

This suppresses small potentiometer jitter at any throttle position while still allowing real movement once the accumulated change exceeds the threshold.

## Current chosen value

The profile uses:

```json
"hold_threshold": 0.03
```

Reasoning:

- `0.015` would not cover the measured `rear3_z40` p2p (`0.023804`).
- Prior idle/reverse measurements were close to `0.031769` p2p.
- `0.03` is the smallest practical starting point before trying a more aggressive `0.035`.

If MSFS still shows small Z/RUD movement in the idle/reverse zone, raise the profile value to:

```json
"hold_threshold": 0.035
```

If throttle movement feels too stepped, lower it to:

```json
"hold_threshold": 0.025
```

## Operational note

After editing `joydiag_profile_final.json`, restart the feeder / scheduled task so the new threshold is loaded:

```powershell
Stop-ScheduledTask -TaskName vJoyFeeder
Start-ScheduledTask -TaskName vJoyFeeder
```
