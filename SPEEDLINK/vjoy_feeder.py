# -*- coding: utf-8 -*-
"""Profile-driven winmm -> vJoy feeder.

Windows-only runtime module for feeding a physical winmm-compatible game
controller into a vJoy device with a JSON correction profile. The code is not
hard-bound to a specific joystick: device selection comes from the profile and
can be overridden from CLI.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from ctypes import wintypes
from pathlib import Path
from typing import Any

from joy_core import (
    AXES,
    apply_profile_axis,
    axis_stats,
    is_safe_autocenter,
    normalize_with_calibrated_range,
    to_vjoy,
)

if os.name == "nt":
    winmm = ctypes.windll.winmm
else:
    winmm = None

JOYERR_NOERROR = 0
JOY_RETURNALL = 0x000000FF
JOY_POVCENTERED = 0xFFFF
MAXPNAMELEN = 32
MAX_JOYSTICKOEMVXD = 260

DEFAULT_PROFILE = "joydiag_profile_final.json"
DEFAULT_PAUSE_FILE = "vjoy_feeder.pause"
SAMPLE_HZ = 100
RECONNECT_SLEEP = 1.0

# Internal axis names:
#   X/Y/Z are vJoy X/Y/Z.
#   R is vJoy Rx, U is vJoy Ry, V is vJoy Rz.
HID_USAGE = {
    "X": 0x30,
    "Y": 0x31,
    "Z": 0x32,
    "R": 0x33,   # Rx
    "U": 0x34,   # Ry
    "V": 0x35,   # Rz
}

OUTPUT_AXIS_ALIASES = {
    "X": "X",
    "Y": "Y",
    "Z": "Z",
    "R": "R",
    "RX": "R",
    "U": "U",
    "RY": "U",
    "V": "V",
    "RZ": "V",
}


class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD),
        ("dwYpos", wintypes.DWORD),
        ("dwZpos", wintypes.DWORD),
        ("dwRpos", wintypes.DWORD),
        ("dwUpos", wintypes.DWORD),
        ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD),
        ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("dwReserved2", wintypes.DWORD),
    ]


class JOYCAPS(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("szPname", ctypes.c_char * MAXPNAMELEN),
        ("wXmin", wintypes.UINT), ("wXmax", wintypes.UINT),
        ("wYmin", wintypes.UINT), ("wYmax", wintypes.UINT),
        ("wZmin", wintypes.UINT), ("wZmax", wintypes.UINT),
        ("wNumButtons", wintypes.UINT),
        ("wPeriodMin", wintypes.UINT), ("wPeriodMax", wintypes.UINT),
        ("wRmin", wintypes.UINT), ("wRmax", wintypes.UINT),
        ("wUmin", wintypes.UINT), ("wUmax", wintypes.UINT),
        ("wVmin", wintypes.UINT), ("wVmax", wintypes.UINT),
        ("wCaps", wintypes.UINT),
        ("wMaxAxes", wintypes.UINT),
        ("wNumAxes", wintypes.UINT),
        ("wMaxButtons", wintypes.UINT),
        ("szRegKey", ctypes.c_char * MAXPNAMELEN),
        ("szOEMVxD", ctypes.c_char * MAX_JOYSTICKOEMVXD),
    ]


AXIS_FIELDS = {
    "X": ("dwXpos", "wXmin", "wXmax"),
    "Y": ("dwYpos", "wYmin", "wYmax"),
    "Z": ("dwZpos", "wZmin", "wZmax"),
    "R": ("dwRpos", "wRmin", "wRmax"),
    "U": ("dwUpos", "wUmin", "wUmax"),
    "V": ("dwVpos", "wVmin", "wVmax"),
}


def require_windows() -> bool:
    return winmm is not None


def parse_int_auto(value: str | int | None) -> int | None:
    """Parse decimal or 0x-prefixed integer values used for VID/PID/ids."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    return int(str(value).strip(), 0)


def format_vidpid(vid: int | None, pid: int | None) -> str:
    if vid is None or pid is None:
        return "VID/PID: не задан"
    return f"VID_{vid:04X}&PID_{pid:04X}"


def device_name(caps: JOYCAPS) -> str:
    try:
        return caps.szPname.decode("cp1251", errors="replace").strip("\x00").strip() or "Joystick"
    except Exception:
        return "Joystick"


def device_vidpid(caps: JOYCAPS) -> tuple[int, int]:
    return int(caps.wMid), int(caps.wPid)


def read_raw(joy_id: int) -> JOYINFOEX | None:
    if not require_windows():
        return None
    info = JOYINFOEX()
    info.dwSize = ctypes.sizeof(JOYINFOEX)
    info.dwFlags = JOY_RETURNALL
    rc = winmm.joyGetPosEx(int(joy_id), ctypes.byref(info))
    return info if rc == JOYERR_NOERROR else None


def get_caps(joy_id: int) -> JOYCAPS | None:
    if not require_windows():
        return None
    caps = JOYCAPS()
    rc = winmm.joyGetDevCapsA(int(joy_id), ctypes.byref(caps), ctypes.sizeof(JOYCAPS))
    return caps if rc == JOYERR_NOERROR else None


def enumerate_devices() -> list[tuple[int, JOYCAPS]]:
    if not require_windows():
        return []
    found: list[tuple[int, JOYCAPS]] = []
    n = max(16, int(winmm.joyGetNumDevs()))
    for joy_id in range(n):
        if read_raw(joy_id) is None:
            continue
        caps = get_caps(joy_id)
        if caps is not None:
            found.append((joy_id, caps))
    return found


def norm_axis(info: JOYINFOEX, caps: JOYCAPS, axis: str) -> float:
    posf, minf, maxf = AXIS_FIELDS[axis]
    raw = getattr(info, posf)
    lo = getattr(caps, minf)
    hi = getattr(caps, maxf)
    if hi <= lo:
        return 0.0
    return max(-1.0, min(1.0, (raw - lo) / (hi - lo) * 2.0 - 1.0))


def pov_to_vjoy_discrete(dw_pov: int) -> int:
    """Convert winmm POV hundredths-of-degree to vJoy discrete POV index."""
    if int(dw_pov) == JOY_POVCENTERED:
        return -1
    degrees = (int(dw_pov) / 100.0) % 360.0
    # vJoy discrete POV: 0=North, 1=East, 2=South, 3=West.
    return int((degrees + 45.0) // 90.0) % 4


def load_profile(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        profile = json.load(file)
    if not isinstance(profile, dict) or not isinstance(profile.get("correction"), dict):
        raise ValueError("Profile must be a JSON object with a 'correction' object")
    return profile


def profile_device_ids(profile: Mapping[str, Any]) -> tuple[int | None, int | None]:
    device = profile.get("device") if isinstance(profile.get("device"), Mapping) else {}
    vid = parse_int_auto(device.get("vid"))
    pid = parse_int_auto(device.get("pid"))
    return vid, pid


def normalize_output_axis_name(axis: str) -> str:
    """Normalize profile output axis names to internal vJoy axis names.

    Profiles may use either internal names (R/U/V) or user-facing vJoy names
    (Rx/Ry/Rz). R means vJoy Rx, U means vJoy Ry, V means vJoy Rz.
    """
    key = str(axis).strip().upper()
    normalized = OUTPUT_AXIS_ALIASES.get(key)
    if normalized is None:
        raise ValueError(f"Unknown vJoy output axis '{axis}'. Use X, Y, Z, Rx, Ry, or Rz.")
    return normalized


def output_axis_map(profile: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return physical-axis -> vJoy-output-axis mapping from profile.

    Default is identity: X->X, Y->Y, Z->Z, R->Rx, U->Ry, V->Rz.
    A source axis can be duplicated to multiple vJoy axes, for example:

        "output_map": {"X": ["X", "Rx"], "R": []}

    This is useful for no-pedals flight setups where one physical X axis should
    drive aileron, rudder, and nose-wheel steering while physical twist is ignored.
    """
    raw_map = profile.get("output_map")
    result: dict[str, list[str]] = {}
    for source_axis in AXES:
        raw_targets: Any = [source_axis]
        if isinstance(raw_map, Mapping) and source_axis in raw_map:
            raw_targets = raw_map[source_axis]

        if raw_targets is None or raw_targets is False:
            result[source_axis] = []
            continue
        if isinstance(raw_targets, str):
            target_values: Sequence[Any] = [raw_targets]
        elif isinstance(raw_targets, Sequence):
            target_values = raw_targets
        else:
            raise ValueError(f"output_map.{source_axis} must be a string, array, null, or false")

        targets: list[str] = []
        for target in target_values:
            normalized = normalize_output_axis_name(str(target))
            if normalized not in targets:
                targets.append(normalized)
        result[source_axis] = targets
    return result


def apply_output_map(source_outputs: Mapping[str, float], profile: Mapping[str, Any]) -> dict[str, float]:
    """Map corrected physical-axis values to vJoy output-axis values.

    Unmapped vJoy axes are explicitly centered (0.0), so disabling a source axis
    does not leave stale vJoy state behind.
    """
    mapped = output_axis_map(profile)
    destination_outputs: dict[str, float] = {axis: 0.0 for axis in AXES}
    for source_axis in AXES:
        value = float(source_outputs.get(source_axis, 0.0))
        for target_axis in mapped[source_axis]:
            destination_outputs[target_axis] = value
    return destination_outputs


def hold_threshold(correction: Mapping[str, Any] | None) -> float:
    """Return per-axis hold/anti-jitter threshold in normalized [-1..1] units.

    `hold_threshold` is the preferred profile key. `jitter_deadband` is kept as
    an alias because early docs/discussions used both names.
    """
    if not isinstance(correction, Mapping):
        return 0.0
    raw = correction.get("hold_threshold", correction.get("jitter_deadband", 0.0))
    try:
        threshold = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, threshold)


def apply_hold_filter(axis: str, value: float, correction: Mapping[str, Any] | None, hold_state: dict[str, float]) -> float:
    """Suppress small axis changes by holding the last sent value.

    This is intended for noisy throttle/slider axes: tiny movement below the
    threshold is treated as potentiometer jitter, while larger accumulated
    changes still pass through so the throttle remains usable.
    """
    threshold = hold_threshold(correction)
    if threshold <= 0.0:
        return value

    previous = hold_state.get(axis)
    if previous is None:
        hold_state[axis] = value
        return value

    if abs(value - previous) < threshold:
        return previous

    hold_state[axis] = value
    return value


def pause_axis_value(axis: str, correction: Mapping[str, Any] | None, last_outputs: Mapping[str, float]) -> float:
    """Return the vJoy value to send while feeder input is paused.

    Safe pause centers self-centering axes, keeps throttle/slider axes at their
    last accepted output, releases buttons, and neutralizes POV. This makes it
    safe to move the physical stick on the desk without sending those movements
    to the simulator.
    """
    if isinstance(correction, Mapping) and correction.get("type") == "throttle":
        return float(last_outputs.get(axis, 0.0))
    return 0.0


def select_device(profile: Mapping[str, Any], *, joy_id: int | None = None, vid: int | None = None, pid: int | None = None) -> tuple[int, JOYCAPS]:
    """Select physical device by explicit joy id, CLI VID/PID, profile VID/PID, or single device fallback."""
    devices = enumerate_devices()
    if joy_id is not None:
        caps = get_caps(joy_id)
        if caps is None or read_raw(joy_id) is None:
            raise RuntimeError(f"winmm device id {joy_id} is not available")
        return joy_id, caps

    profile_vid, profile_pid = profile_device_ids(profile)
    target_vid = vid if vid is not None else profile_vid
    target_pid = pid if pid is not None else profile_pid

    if target_vid is not None and target_pid is not None:
        for candidate_id, caps in devices:
            c_vid, c_pid = device_vidpid(caps)
            if c_vid == target_vid and c_pid == target_pid:
                return candidate_id, caps
        raise RuntimeError(f"Physical joystick not found: {format_vidpid(target_vid, target_pid)}")

    if len(devices) == 1:
        return devices[0]

    if not devices:
        raise RuntimeError("No winmm-compatible game controllers found")

    raise RuntimeError(
        "Multiple controllers found and profile has no VID/PID. "
        "Use --list-devices, then pass --joy-id or --vid/--pid."
    )


def describe_devices() -> str:
    devices = enumerate_devices()
    if not devices:
        return "No winmm-compatible game controllers found."
    lines = []
    for joy_id, caps in devices:
        vid, pid = device_vidpid(caps)
        lines.append(
            f"[{joy_id}] {device_name(caps)}  VID_{vid:04X}&PID_{pid:04X}  "
            f"axes={int(caps.wNumAxes)} buttons={int(caps.wNumButtons)}"
        )
    return "\n".join(lines)


class Logger:
    def __init__(self, path: str | Path, quiet: bool = False):
        self.path = Path(path)
        self.quiet = quiet

    def __call__(self, message: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
        if not self.quiet:
            print(line, flush=True)


class VJoyDevice:
    def __init__(self, dll_path: str | Path, device_id: int):
        self.dll_path = str(dll_path)
        self.device_id = int(device_id)
        self.dll = ctypes.WinDLL(self.dll_path)
        self._bind()
        if not self.dll.AcquireVJD(self.device_id):
            raise RuntimeError(f"Could not acquire vJoy #{self.device_id}; it may be busy or disabled")
        self.reset()

    def _bind(self) -> None:
        self.dll.AcquireVJD.argtypes = [wintypes.UINT]
        self.dll.AcquireVJD.restype = wintypes.BOOL
        self.dll.RelinquishVJD.argtypes = [wintypes.UINT]
        self.dll.RelinquishVJD.restype = None
        self.dll.SetAxis.argtypes = [wintypes.LONG, wintypes.UINT, wintypes.UINT]
        self.dll.SetAxis.restype = wintypes.BOOL
        self.dll.SetBtn.argtypes = [wintypes.BOOL, wintypes.UINT, ctypes.c_ubyte]
        self.dll.SetBtn.restype = wintypes.BOOL
        self.dll.SetDiscPov.argtypes = [ctypes.c_int, wintypes.UINT, ctypes.c_ubyte]
        self.dll.SetDiscPov.restype = wintypes.BOOL
        if hasattr(self.dll, "ResetVJD"):
            self.dll.ResetVJD.argtypes = [wintypes.UINT]
            self.dll.ResetVJD.restype = wintypes.BOOL

    def reset(self) -> None:
        if hasattr(self.dll, "ResetVJD"):
            self.dll.ResetVJD(self.device_id)

    def set_axis(self, usage: int, value: int) -> None:
        self.dll.SetAxis(int(value), self.device_id, int(usage))

    def set_button(self, number: int, pressed: bool) -> None:
        self.dll.SetBtn(bool(pressed), self.device_id, int(number))

    def set_pov(self, number: int, value: int) -> None:
        self.dll.SetDiscPov(int(value), self.device_id, int(number))

    def close(self) -> None:
        self.dll.RelinquishVJD(self.device_id)


def find_vjoy_dll(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    base = Path(__file__).resolve().parent
    candidates += [
        base / "vJoyInterface.dll",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "vJoy" / "x64" / "vJoyInterface.dll",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "vJoy" / "vJoyInterface.dll",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "vJoy" / "x64" / "vJoyInterface.dll",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "vJoy" / "vJoyInterface.dll",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("vJoyInterface.dll not found; pass --vjoy-dll C:\\path\\vJoyInterface.dll")


def sample_autocenter(joy_id: int, caps: JOYCAPS, profile: Mapping[str, Any], seconds: float, log: Logger) -> dict[str, float]:
    correction = profile.get("correction", {})
    data: dict[str, list[float]] = {axis: [] for axis in AXES}
    count = max(1, int(seconds * SAMPLE_HZ))
    delay = 1.0 / SAMPLE_HZ
    for _ in range(count):
        info = read_raw(joy_id)
        if info is not None:
            for axis in AXES:
                corr = correction.get(axis, {}) if isinstance(correction, Mapping) else {}
                if isinstance(corr, Mapping) and corr.get("type") == "throttle":
                    continue
                raw = norm_axis(info, caps, axis)
                data[axis].append(normalize_with_calibrated_range(raw, corr if isinstance(corr, Mapping) else None))
        time.sleep(delay)

    centers: dict[str, float] = {}
    for axis, values in data.items():
        if not values:
            continue
        st = axis_stats(values)
        if is_safe_autocenter(st):
            centers[axis] = st["mean"]
            log(f"auto-center {axis}: {st['mean']:+.4f} spread={st['spread']:.4f}")
        else:
            log(f"auto-center {axis}: rejected mean={st['mean']:+.4f} spread={st['spread']:.4f}")
    return centers


def feed_once(
    vjoy: VJoyDevice,
    info: JOYINFOEX,
    caps: JOYCAPS,
    profile: Mapping[str, Any],
    runtime_centers: Mapping[str, float],
    hold_state: dict[str, float] | None = None,
) -> dict[str, float]:
    correction = profile.get("correction", {})
    source_outputs: dict[str, float] = {}
    for axis in AXES:
        corr = correction.get(axis) if isinstance(correction, Mapping) else None
        raw = norm_axis(info, caps, axis)
        fixed = apply_profile_axis(raw, corr if isinstance(corr, Mapping) else None, runtime_center=runtime_centers.get(axis))
        if hold_state is not None:
            fixed = apply_hold_filter(axis, fixed, corr if isinstance(corr, Mapping) else None, hold_state)
        source_outputs[axis] = fixed

    destination_outputs = apply_output_map(source_outputs, profile)
    for axis in AXES:
        vjoy.set_axis(HID_USAGE[axis], to_vjoy(destination_outputs[axis]))

    max_buttons = min(32, int(caps.wNumButtons))
    for button in range(max_buttons):
        vjoy.set_button(button + 1, bool(info.dwButtons & (1 << button)))

    vjoy.set_pov(1, pov_to_vjoy_discrete(info.dwPOV))
    return source_outputs


def feed_pause_once(vjoy: VJoyDevice, profile: Mapping[str, Any], caps: JOYCAPS | None, last_outputs: Mapping[str, float]) -> None:
    """Send safe vJoy output while physical input is paused."""
    correction = profile.get("correction", {})
    source_outputs: dict[str, float] = {}
    for axis in AXES:
        corr = correction.get(axis) if isinstance(correction, Mapping) else None
        source_outputs[axis] = pause_axis_value(axis, corr if isinstance(corr, Mapping) else None, last_outputs)

    destination_outputs = apply_output_map(source_outputs, profile)
    for axis in AXES:
        vjoy.set_axis(HID_USAGE[axis], to_vjoy(destination_outputs[axis]))

    max_buttons = 32 if caps is None else min(32, int(caps.wNumButtons))
    for button in range(max_buttons):
        vjoy.set_button(button + 1, False)
    vjoy.set_pov(1, -1)


def resolve_pause_file(profile_path: Path, pause_file_arg: str | None) -> Path:
    raw = Path(pause_file_arg or DEFAULT_PAUSE_FILE)
    if raw.is_absolute():
        return raw
    return profile_path.with_name(str(raw))


def run(args: argparse.Namespace) -> int:
    if not require_windows():
        print("vjoy_feeder.py uses winmm/vJoy and runs only on Windows.", file=sys.stderr)
        return 2

    profile_path = Path(args.profile or DEFAULT_PROFILE)
    if not profile_path.is_absolute():
        profile_path = Path(__file__).resolve().parent / profile_path
    profile = load_profile(profile_path)
    # Validate output_map at startup so configuration errors are explicit.
    output_axis_map(profile)

    if args.list_devices:
        print(describe_devices())
        return 0

    pause_file = resolve_pause_file(profile_path, args.pause_file)
    log_path = Path(args.log) if args.log else profile_path.with_name("vjoy_feeder.log")
    log = Logger(log_path, quiet=args.quiet)
    log(f"profile: {profile_path}")
    log(f"pause file: {pause_file}")

    vjoy_target = int(args.vjoy_target or profile.get("vjoy_target", 1))
    vjoy_dll = find_vjoy_dll(args.vjoy_dll)
    vjoy = VJoyDevice(vjoy_dll, vjoy_target)
    log(f"vJoy #{vjoy_target} acquired via {vjoy_dll}")

    cli_vid = parse_int_auto(args.vid)
    cli_pid = parse_int_auto(args.pid)
    if (cli_vid is None) ^ (cli_pid is None):
        raise ValueError("Pass --vid and --pid together, or neither")

    joy_id_arg = parse_int_auto(args.joy_id)
    delay = 1.0 / float(args.hz)
    runtime_centers: dict[str, float] = {}
    hold_state: dict[str, float] = {}
    last_outputs: dict[str, float] = {}
    paused = False
    current_id: int | None = None
    current_caps: JOYCAPS | None = None

    try:
        while True:
            if pause_file.exists():
                if not paused:
                    paused = True
                    log("input paused")
                feed_pause_once(vjoy, profile, current_caps, last_outputs)
                time.sleep(delay)
                continue

            if paused:
                paused = False
                log("input resumed; re-acquiring device and auto-centering")
                runtime_centers = {}
                hold_state = {}
                last_outputs = {}
                current_id = None
                current_caps = None

            if current_id is None or current_caps is None or read_raw(current_id) is None:
                try:
                    current_id, current_caps = select_device(profile, joy_id=joy_id_arg, vid=cli_vid, pid=cli_pid)
                    vid, pid = device_vidpid(current_caps)
                    log(f"physical device: id={current_id} {device_name(current_caps)} VID_{vid:04X}&PID_{pid:04X}")
                    runtime_centers = {}
                    hold_state = {}
                    last_outputs = {}
                    if not args.no_autocenter:
                        runtime_centers = sample_autocenter(current_id, current_caps, profile, float(args.autocenter_secs), log)
                except Exception as exc:
                    log(f"waiting for physical device: {exc}")
                    time.sleep(RECONNECT_SLEEP)
                    continue

            info = read_raw(current_id)
            if info is None:
                log("physical device disconnected")
                current_id = None
                current_caps = None
                hold_state = {}
                last_outputs = {}
                time.sleep(RECONNECT_SLEEP)
                continue

            last_outputs = feed_once(vjoy, info, current_caps, profile, runtime_centers, hold_state)
            time.sleep(delay)
    except KeyboardInterrupt:
        log("stopped by user")
        return 0
    finally:
        vjoy.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile-driven winmm -> vJoy feeder")
    parser.add_argument("profile", nargs="?", default=DEFAULT_PROFILE, help="Correction profile JSON path")
    parser.add_argument("--list-devices", action="store_true", help="List visible winmm game controllers and exit")
    parser.add_argument("--vid", help="Override physical device VID, e.g. 0x07B5")
    parser.add_argument("--pid", help="Override physical device PID, e.g. 0x0317")
    parser.add_argument("--joy-id", help="Use exact winmm device id instead of VID/PID matching")
    parser.add_argument("--vjoy-target", type=int, help="Override vJoy device id from profile")
    parser.add_argument("--vjoy-dll", help="Path to vJoyInterface.dll")
    parser.add_argument("--log", help="Log file path")
    parser.add_argument("--pause-file", help="Pause flag file path, default vjoy_feeder.pause next to the profile")
    parser.add_argument("--hz", type=int, default=SAMPLE_HZ, help="Feed rate, default 100")
    parser.add_argument("--no-autocenter", action="store_true", help="Disable runtime auto-center")
    parser.add_argument("--autocenter-secs", type=float, default=1.2, help="Runtime auto-center sample length")
    parser.add_argument("--quiet", action="store_true", help="Do not print log lines to console")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
