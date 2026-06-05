# -*- coding: utf-8 -*-
"""Pure correction/math helpers for SPEEDLINK joystick tools.

This module is intentionally free of Windows APIs so the risky part of the
project (axis correction math) can be unit-tested anywhere. Runtime scripts such
as joy_diag.py and vjoy_feeder.py can import these helpers, but the functions
also keep backward-compatible names/formulas with the original monolithic code.
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence

AXES = ("X", "Y", "Z", "R", "U", "V")
VMIN = 1
VMAX = 32768


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """Clamp a normalized axis value."""
    return max(lo, min(hi, float(value)))


def axis_stats(vals: Sequence[float]) -> dict[str, float]:
    """Return center/noise/drift statistics for a normalized axis sample."""
    if not vals:
        return dict(mean=0.0, minv=0.0, maxv=0.0, spread=0.0, sd=0.0, drift=0.0)

    values = [float(v) for v in vals]
    mean = sum(values) / len(values)
    mn, mx = min(values), max(values)
    sd = statistics.pstdev(values) if len(values) > 1 else 0.0
    k = max(1, len(values) // 10)
    drift = (sum(values[-k:]) / k) - (sum(values[:k]) / k)
    return dict(mean=mean, minv=mn, maxv=mx, spread=mx - mn, sd=sd, drift=drift)


def autogen_correction(st: Mapping[str, float]) -> dict[str, Any]:
    """Build a correction profile for one axis from rest statistics."""
    mean = float(st.get("mean", 0.0))
    spread = float(st.get("spread", 0.0))
    sd = float(st.get("sd", 0.0))

    if abs(mean) > 0.9 and spread < 0.02:
        return {
            "type": "throttle",
            "center_offset": 0.0,
            "deadzone": 0.0,
            "scale_pos": 1.0,
            "scale_neg": 1.0,
            "invert": False,
        }

    center_offset = -mean
    pos_reach = 1.0 + center_offset
    neg_reach = 1.0 - center_offset
    scale_pos = (1.0 / pos_reach) if pos_reach > 0.05 else 1.0
    scale_neg = (1.0 / neg_reach) if neg_reach > 0.05 else 1.0
    deadzone = spread / 2.0 + 2.0 * sd + 0.005

    return {
        "type": "stick",
        "center_offset": center_offset,
        "deadzone": deadzone,
        "scale_pos": scale_pos,
        "scale_neg": scale_neg,
        "invert": False,
    }


def _with_runtime_center(correction: Mapping[str, Any], runtime_center: float | None) -> dict[str, Any]:
    c = dict(correction)
    if runtime_center is not None and c.get("type") != "throttle":
        c["center_offset"] = -float(runtime_center)
    return c


def apply_correction(norm: float, correction: Mapping[str, Any] | None, *, runtime_center: float | None = None) -> float:
    """Apply saved axis correction to a normalized value in [-1, 1]."""
    if not correction:
        return clamp(norm)

    c = _with_runtime_center(correction, runtime_center)

    if c.get("type") == "throttle":
        value = float(norm)
        if c.get("invert"):
            value = -value
        return clamp(value)

    x = float(norm) + float(c.get("center_offset", 0.0))
    deadzone = float(c.get("deadzone", 0.0) or 0.0)

    if deadzone >= 1.0:
        x = 0.0
    elif deadzone > 0 and abs(x) <= deadzone:
        x = 0.0
    elif deadzone > 0:
        x = (abs(x) - deadzone) / (1.0 - deadzone) * (1.0 if x > 0 else -1.0)

    scale = float(c.get("scale_pos", 1.0) if x >= 0 else c.get("scale_neg", 1.0))
    x = clamp(x * scale)

    if c.get("invert"):
        x = -x
    return clamp(x)


def normalize_from_range(raw: float, lo: float, hi: float) -> float:
    """Normalize a raw or normalized value to [-1, 1] using a source range."""
    lo = float(lo)
    hi = float(hi)
    if hi <= lo:
        return 0.0
    return clamp((float(raw) - lo) / (hi - lo) * 2.0 - 1.0)


def normalize_with_calibrated_range(norm: float, correction: Mapping[str, Any] | None) -> float:
    """Remap a normalized value through optional calibrated_min/max metadata."""
    if not correction:
        return clamp(norm)

    cmin = correction.get("calibrated_min")
    cmax = correction.get("calibrated_max")
    if cmin is None or cmax is None:
        return clamp(norm)

    try:
        lo = float(cmin)
        hi = float(cmax)
    except (TypeError, ValueError):
        return clamp(norm)

    if hi - lo < 0.05:
        return clamp(norm)

    return normalize_from_range(norm, lo, hi)


def apply_profile_axis(norm: float, correction: Mapping[str, Any] | None, *, runtime_center: float | None = None) -> float:
    """Apply edge remap (if present) and then center/deadzone correction."""
    remapped = normalize_with_calibrated_range(norm, correction)
    return apply_correction(remapped, correction, runtime_center=runtime_center)


def to_vjoy(value: float, vmin: int = VMIN, vmax: int = VMAX) -> int:
    """Convert normalized [-1, 1] axis value to vJoy integer range."""
    fixed = clamp(value)
    return int(round((fixed + 1.0) / 2.0 * (vmax - vmin) + vmin))


def is_safe_autocenter(stats: Mapping[str, float], *, max_spread: float = 0.06, max_abs_center: float = 0.6) -> bool:
    """Validate runtime auto-center sample before trusting it."""
    return abs(float(stats.get("mean", 0.0))) <= max_abs_center and float(stats.get("spread", 0.0)) <= max_spread


def build_profile(device: Mapping[str, Any], corrections: Mapping[str, Mapping[str, Any]], *, vjoy_target: int = 1) -> dict[str, Any]:
    """Build a profile shape consistently."""
    return {
        "device": dict(device),
        "vjoy_target": int(vjoy_target),
        "correction": {axis: dict(corrections[axis]) for axis in corrections},
    }
