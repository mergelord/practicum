# -*- coding: utf-8 -*-
"""JoyDiag — GUI диагностики джойстика и подготовки профиля коррекции.

Windows-only диагностический модуль для winmm-совместимых манипуляторов.
Математика коррекции вынесена в joy_core.py, чтобы joy_diag.py и
vjoy_feeder.py использовали одну и ту же формулу.
"""

from __future__ import annotations

import csv
import ctypes
import datetime
import json
import os
import queue
import time
import threading
from ctypes import wintypes
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk
import tkinter.messagebox as mbox

from joy_core import (
    AXES,
    VMAX,
    VMIN,
    apply_profile_axis,
    autogen_correction,
    axis_stats,
    to_vjoy,
)

try:
    import winreg
except ImportError:  # не Windows
    winreg = None

if os.name == "nt":
    winmm = ctypes.windll.winmm
else:
    winmm = None

JOYERR_NOERROR = 0
JOY_RETURNALL = 0x000000FF
JOY_POVCENTERED = 0xFFFF
MAXPNAMELEN = 32
MAX_JOYSTICKOEMVXD = 260

SAMPLE_HZ = 100
REST_SECONDS = 8
EDGE_SECONDS = 12
JITTER_SECONDS = 60
RECONNECT_SECS = 1.5
PORT_JITTER_SECS = 60

VJOY_AXIS_MAP = {"X": "X", "Y": "Y", "Z": "Z", "R": "RX", "U": "RY", "V": "RZ"}


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


# ---------------------------------------------------------------- winmm -----

def require_windows() -> bool:
    return winmm is not None


def get_caps(joy_id: int) -> JOYCAPS | None:
    if not require_windows():
        return None
    caps = JOYCAPS()
    rc = winmm.joyGetDevCapsA(int(joy_id), ctypes.byref(caps), ctypes.sizeof(JOYCAPS))
    return caps if rc == JOYERR_NOERROR else None


def read_raw(joy_id: int) -> JOYINFOEX | None:
    if not require_windows():
        return None
    info = JOYINFOEX()
    info.dwSize = ctypes.sizeof(JOYINFOEX)
    info.dwFlags = JOY_RETURNALL
    rc = winmm.joyGetPosEx(int(joy_id), ctypes.byref(info))
    return info if rc == JOYERR_NOERROR else None


def norm_axis(info: JOYINFOEX, caps: JOYCAPS, axis: str) -> float:
    posf, minf, maxf = AXIS_FIELDS[axis]
    raw = getattr(info, posf)
    lo = getattr(caps, minf)
    hi = getattr(caps, maxf)
    if hi <= lo:
        return 0.0
    return max(-1.0, min(1.0, (raw - lo) / (hi - lo) * 2.0 - 1.0))


def device_name(caps: JOYCAPS) -> str:
    try:
        return caps.szPname.decode("cp1251", errors="replace").strip("\x00").strip() or "Joystick"
    except Exception:
        return "Joystick"


def device_vidpid(caps: JOYCAPS) -> tuple[int, int]:
    return int(caps.wMid), int(caps.wPid)


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


# ------------------------------------------------------------ Registry -----

JOY_OEM = r"System\CurrentControlSet\Control\MediaProperties\PrivateProperties\Joystick\OEM"
DINPUT = r"System\CurrentControlSet\Control\MediaProperties\PrivateProperties\DirectInput"


def _dev_key(vid: int, pid: int) -> str:
    return f"VID_{vid:04X}&PID_{pid:04X}"


def _reg_hives():
    return [("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE)]


def _reg_targets(vid: int, pid: int):
    dev = _dev_key(vid, pid)
    return [("Joystick/OEM (winmm)", f"{JOY_OEM}\\{dev}"), ("DirectInput", f"{DINPUT}\\{dev}")]


def _enum_values(key):
    out, i = {}, 0
    while True:
        try:
            name, val, _ = winreg.EnumValue(key, i)
        except OSError:
            break
        out[name] = val
        i += 1
    return out


def _subkeys(hive, path):
    try:
        key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except FileNotFoundError:
        return None
    names, i = [], 0
    while True:
        try:
            names.append(winreg.EnumKey(key, i))
        except OSError:
            break
        i += 1
    winreg.CloseKey(key)
    return names


def find_windows_calibration(vid: int, pid: int):
    if winreg is None:
        return []
    found = []
    for hive_name, hive in _reg_hives():
        for label, path in _reg_targets(vid, pid):
            try:
                key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            except FileNotFoundError:
                continue
            except PermissionError:
                found.append(dict(hive=hive_name, label=label, path=path, status="нет доступа", values={}))
                continue
            values = _enum_values(key)
            winreg.CloseKey(key)
            found.append(dict(hive=hive_name, label=label, path=path, status="ЕСТЬ", values=values))
    return found


def _delete_tree(hive, path):
    subs = _subkeys(hive, path)
    if subs is None:
        return False
    for sub in subs:
        _delete_tree(hive, f"{path}\\{sub}")
    winreg.DeleteKeyEx(hive, path, winreg.KEY_WOW64_64KEY, 0)
    return True


def delete_windows_calibration(vid: int, pid: int, include_hklm: bool = False):
    if winreg is None:
        return [], ["winreg недоступен"]
    deleted, errors = [], []
    hives = _reg_hives() if include_hklm else _reg_hives()[:1]
    for hive_name, hive in hives:
        for _, path in _reg_targets(vid, pid):
            try:
                if _delete_tree(hive, path):
                    deleted.append(f"{hive_name}\\{path}")
            except PermissionError:
                errors.append(f"{hive_name}\\{path} — нужны права администратора")
            except FileNotFoundError:
                pass
    return deleted, errors


# ------------------------------------------------------------------ GUI -----

class JoyDiagApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("JoyDiag 2.2 — диагностика и коррекция осей")
        root.geometry("980x860")

        self.devices: list[tuple[int, JOYCAPS]] = []
        self.joy_id: int | None = None
        self.caps: JOYCAPS | None = None
        self.correction: dict[str, dict] = {}
        self.ranges: dict[str, tuple[float, float]] = {}
        self.last_rest: dict[str, dict[str, float]] = {}
        self.vjoy_target = 1
        self.busy = False
        self.result_q: queue.Queue = queue.Queue()
        self._pyvjoy_dev = None
        self._feed_running = False

        self._build_ui()
        self.refresh_devices()
        self.root.after(50, self._poll_queue)
        self.root.after(40, self._live_loop)

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Устройство:").pack(side="left")
        self.dev_var = tk.StringVar()
        self.dev_combo = ttk.Combobox(top, textvariable=self.dev_var, width=58, state="readonly")
        self.dev_combo.pack(side="left", padx=4)
        self.dev_combo.bind("<<ComboboxSelected>>", lambda _e: self._select_device())
        ttk.Button(top, text="Обновить", command=self.refresh_devices).pack(side="left", padx=4)
        self.info_var = tk.StringVar(value="—")
        ttk.Label(self.root, textvariable=self.info_var, foreground="#555").pack(fill="x", padx=10)

        live = ttk.LabelFrame(self.root, text="Живой просмотр (сырое → с коррекцией из joy_core.py)")
        live.pack(fill="x", padx=8, pady=6)
        self.axis_canvas: dict[str, tk.Canvas] = {}
        self.axis_lbl: dict[str, tk.StringVar] = {}
        for axis in AXES:
            row = ttk.Frame(live)
            row.pack(fill="x", padx=6, pady=1)
            ttk.Label(row, text=axis, width=3).pack(side="left")
            canvas = tk.Canvas(row, width=420, height=18, bg="white", highlightthickness=1, highlightbackground="#ccc")
            canvas.pack(side="left", padx=4)
            self.axis_canvas[axis] = canvas
            label = tk.StringVar(value="—")
            ttk.Label(row, textvariable=label, width=42, font=("Consolas", 9)).pack(side="left")
            self.axis_lbl[axis] = label
        self.btn_var = tk.StringVar(value="Кнопки: —    POV: —")
        ttk.Label(live, textvariable=self.btn_var, font=("Consolas", 9)).pack(fill="x", padx=8, pady=3)

        diag = ttk.LabelFrame(self.root, text="Диагностика и профиль")
        diag.pack(fill="x", padx=8, pady=6)
        r1 = ttk.Frame(diag)
        r1.pack(fill="x", padx=4, pady=3)
        ttk.Button(r1, text=f"Замерить покой ({REST_SECONDS}с)", command=self.measure_rest).pack(side="left", padx=3)
        ttk.Button(r1, text=f"Калибровка краёв ({EDGE_SECONDS}с)", command=self.measure_edges).pack(side="left", padx=3)
        ttk.Button(r1, text="Сохр. JSON", command=self.save_json).pack(side="left", padx=3)
        ttk.Button(r1, text="Сохр. CSV", command=self.save_csv).pack(side="left", padx=3)
        ttk.Button(r1, text="Загрузить JSON", command=self.load_json).pack(side="left", padx=3)
        r2 = ttk.Frame(diag)
        r2.pack(fill="x", padx=4, pady=3)
        ttk.Button(r2, text="Запуск коррекции (pyvjoy)", command=self.start_feed).pack(side="left", padx=3)
        ttk.Button(r2, text="Стоп", command=self.stop_feed).pack(side="left", padx=3)
        ttk.Label(r2, text="(preview без POV; для игры используй vjoy_feeder.py)", foreground="#a00").pack(side="left", padx=6)

        hw = ttk.LabelFrame(self.root, text="Диагностика железа «почему уводит»")
        hw.pack(fill="x", padx=8, pady=6)
        hr = ttk.Frame(hw)
        hr.pack(fill="x", padx=4, pady=3)
        ttk.Button(hr, text=f"Тест дрожания ({JITTER_SECONDS}с)", command=self.jitter_test).pack(side="left", padx=3)
        ttk.Button(hr, text="Калибровка Windows (чтение)", command=self.read_windows_cal).pack(side="left", padx=3)
        ttk.Button(hr, text="Сбросить калибровку Windows", command=self.reset_windows_cal).pack(side="left", padx=3)

        self.reconnect = ReconnectTest(self.root, self)

        logf = ttk.LabelFrame(self.root, text="Журнал")
        logf.pack(fill="both", expand=True, padx=8, pady=6)
        self.log = tk.Text(logf, height=8, font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    def refresh_devices(self) -> None:
        self.devices = enumerate_devices()
        items = []
        for joy_id, caps in self.devices:
            vid, pid = device_vidpid(caps)
            items.append(f"[{joy_id}] {device_name(caps)}  VID_{vid:04X}&PID_{pid:04X}")
        self.dev_combo["values"] = items
        if items:
            self.dev_combo.current(0)
            self._select_device()
        else:
            self.info_var.set("Манипуляторы не найдены" if require_windows() else "Только Windows: winmm недоступен")
        self._logln(f"Найдено устройств: {len(items)}")

    def _select_device(self) -> None:
        idx = self.dev_combo.current()
        if idx < 0 or idx >= len(self.devices):
            return
        self.joy_id, self.caps = self.devices[idx]
        vid, pid = device_vidpid(self.caps)
        self.info_var.set(
            f"id {self.joy_id} · {device_name(self.caps)} · VID_{vid:04X}&PID_{pid:04X} · "
            f"осей {self.caps.wNumAxes} · кнопок {self.caps.wNumButtons} · POV {'есть' if self.caps.wCaps else 'нет'}"
        )

    def current_vidpid(self) -> tuple[int, int] | None:
        if self.caps is not None:
            return device_vidpid(self.caps)
        return None

    def _guard(self) -> bool:
        if self.joy_id is None or self.caps is None:
            mbox.showwarning("Нет устройства", "Сначала выбери манипулятор.")
            return False
        if self.busy:
            mbox.showinfo("Занято", "Уже идёт замер, дождись завершения.")
            return False
        return True

    def sample_rest(self, seconds: float, hz: int, axes=None) -> dict[str, list[float]]:
        axes = axes or AXES
        data = {axis: [] for axis in axes}
        if self.joy_id is None or self.caps is None:
            return data
        count = int(seconds * hz)
        delay = 1.0 / hz
        for _ in range(count):
            info = read_raw(self.joy_id)
            if info is not None:
                for axis in axes:
                    data[axis].append(norm_axis(info, self.caps, axis))
            time.sleep(delay)
        return data

    def measure_rest(self) -> None:
        if not self._guard():
            return
        self.busy = True
        self._logln(f"Замер покоя {REST_SECONDS}с — убери руки…")
        self._run_async(lambda: self.sample_rest(REST_SECONDS, SAMPLE_HZ), self._on_rest)

    def _on_rest(self, data: dict[str, list[float]]) -> None:
        self.busy = False
        self.last_rest = {axis: axis_stats(data.get(axis, [])) for axis in AXES}
        self.correction = {axis: autogen_correction(self.last_rest[axis]) for axis in AXES}
        self._logln("Покой измерен. Профиль коррекции сгенерирован через joy_core.py:")
        for axis in AXES:
            st = self.last_rest[axis]
            corr = self.correction[axis]
            self._logln(
                f"  {axis}: center={st['mean']:+.4f} σ={st['sd']:.4f} spread={st['spread']:.4f} "
                f"drift={st['drift']:+.4f} → {corr['type']} off={corr['center_offset']:+.4f} "
                f"dz={corr['deadzone']:.4f} sp={corr['scale_pos']:.3f} sn={corr['scale_neg']:.3f}"
            )

    def measure_edges(self) -> None:
        if not self._guard():
            return
        self.busy = True
        self._logln(f"Калибровка краёв {EDGE_SECONDS}с — гоняй ВСЕ оси до упоров…")
        self._run_async(lambda: self.sample_rest(EDGE_SECONDS, SAMPLE_HZ), self._on_edges)

    def _on_edges(self, data: dict[str, list[float]]) -> None:
        self.busy = False
        for axis in AXES:
            vals = data.get(axis, [])
            if not vals:
                continue
            mn, mx = min(vals), max(vals)
            if (mx - mn) * (VMAX - VMIN) / 2.0 < 8:
                continue
            self.ranges[axis] = (mn, mx)
        text = ", ".join(f"{axis}[{lo:+.2f}..{hi:+.2f}]" for axis, (lo, hi) in self.ranges.items())
        self._logln("Калибровка краёв завершена: " + (text or "(оси не двигали)"))

    def jitter_test(self) -> None:
        if not self._guard():
            return
        self.busy = True
        self._logln(f"Тест дрожания {JITTER_SECONDS}с — НЕ трогай ручку…")
        self._run_async(lambda: self.sample_rest(JITTER_SECONDS, SAMPLE_HZ), self._on_jitter)

    def _on_jitter(self, data: dict[str, list[float]]) -> None:
        self.busy = False
        self._logln("=== Тест дрожания: интерпретация ===")
        for axis in ("X", "Y", "R"):
            st = axis_stats(data.get(axis, []))
            self._logln(
                f"  {axis}: σ={st['sd']:.4f} spread={st['spread']:.4f} drift={st['drift']:+.4f} → {self._jitter_verdict(st)}"
            )

    @staticmethod
    def _jitter_verdict(st: dict[str, float]) -> str:
        if st["sd"] > 0.02 or st["spread"] > 0.08:
            return "высокий шум → износ/грязь потенциометра (чистка/замена)"
        if abs(st["drift"]) > 0.03:
            return "дрейф во времени → проседание USB-питания (убрать хаб, другой порт)"
        if abs(st["mean"]) > 0.02:
            return "стабильный увод при малом шуме → лечится center_offset (механика/калибровка)"
        return "ось стабильна — увод не обнаружен"

    def read_windows_cal(self) -> None:
        if winreg is None:
            mbox.showerror("Реестр", "Модуль winreg недоступен (не Windows?).")
            return
        vidpid = self.current_vidpid()
        if vidpid is None:
            mbox.showwarning("Нет устройства", "Сначала выбери манипулятор.")
            return
        vid, pid = vidpid
        found = [item for item in find_windows_calibration(vid, pid) if item["status"] == "ЕСТЬ"]
        if not found:
            mbox.showinfo("Калибровка Windows", f"Сохранённой калибровки Windows для VID_{vid:04X}&PID_{pid:04X} не найдено.")
            self._logln("Калибровка Windows: НЕ найдена.")
            return
        lines = []
        for item in found:
            lines.append(f"[{item['hive']}] {item['label']}\n    {item['path']}")
            for name, value in item["values"].items():
                shown = value if isinstance(value, str) else f"<{type(value).__name__}, {len(value) if hasattr(value, '__len__') else ''} б>"
                lines.append(f"      {name} = {shown}")
        text = "\n".join(lines)
        mbox.showinfo("Калибровка Windows найдена", text)
        self._logln("Калибровка Windows: НАЙДЕНА\n" + text)

    def reset_windows_cal(self) -> None:
        if winreg is None:
            mbox.showerror("Реестр", "Модуль winreg недоступен (не Windows?).")
            return
        vidpid = self.current_vidpid()
        if vidpid is None:
            mbox.showwarning("Нет устройства", "Сначала выбери манипулятор.")
            return
        vid, pid = vidpid
        found = [item for item in find_windows_calibration(vid, pid) if item["status"] == "ЕСТЬ"]
        if not found:
            mbox.showinfo("Сброс калибровки", "Сохранённой калибровки Windows нет — сбрасывать нечего.")
            return
        paths = "\n".join(f"• {item['hive']}: {item['path']}" for item in found)
        if not mbox.askyesno("Сбросить калибровку Windows?", "Будут удалены пользовательские ветки калибровки:\n\n" + paths + "\n\nУдалять?"):
            return
        deleted, errors = delete_windows_calibration(vid, pid, include_hklm=False)
        msg = ""
        if deleted:
            msg += "Удалено:\n" + "\n".join(deleted)
        if errors:
            msg += "\n\nНе удалено:\n" + "\n".join(errors)
        msg += "\n\nПЕРЕПОДКЛЮЧИ USB, чтобы Windows взяла дефолт."
        mbox.showinfo("Готово", msg)
        self._logln("Сброс калибровки Windows:\n" + msg)

    def _build_profile(self) -> dict:
        vidpid = self.current_vidpid()
        vid, pid = vidpid if vidpid is not None else (None, None)
        corrections = {}
        for axis in AXES:
            corr = dict(self.correction.get(axis, autogen_correction(self.last_rest.get(axis, axis_stats([])))))
            if axis in self.ranges:
                corr["calibrated_min"], corr["calibrated_max"] = self.ranges[axis]
            corrections[axis] = corr
        return {
            "device": {
                "name": device_name(self.caps) if self.caps else "",
                "vid": f"0x{vid:04X}" if vid is not None else None,
                "pid": f"0x{pid:04X}" if pid is not None else None,
                "joy_id": self.joy_id,
            },
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "vjoy_target": self.vjoy_target,
            "correction": corrections,
        }

    def save_json(self) -> None:
        if not self.correction:
            mbox.showinfo("Нет профиля", "Сначала «Замерить покой».")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="joydiag_profile_final.json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as file:
            json.dump(self._build_profile(), file, ensure_ascii=False, indent=2)
        self._logln(f"Профиль сохранён: {path}")

    def save_csv(self) -> None:
        if not self.last_rest:
            mbox.showinfo("Нет данных", "Сначала «Замерить покой».")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="joydiag_rest.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["axis", "mean", "min", "max", "spread", "sigma", "drift"])
            for axis in AXES:
                st = self.last_rest.get(axis, axis_stats([]))
                writer.writerow([axis, f"{st['mean']:.6f}", f"{st['minv']:.6f}", f"{st['maxv']:.6f}", f"{st['spread']:.6f}", f"{st['sd']:.6f}", f"{st['drift']:.6f}"])
        self._logln(f"CSV сохранён: {path}")

    def load_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as file:
            profile = json.load(file)
        self.correction = profile.get("correction", {})
        self.vjoy_target = int(profile.get("vjoy_target", 1))
        self.ranges.clear()
        for axis, corr in self.correction.items():
            if "calibrated_min" in corr and "calibrated_max" in corr:
                self.ranges[axis] = (corr["calibrated_min"], corr["calibrated_max"])
        self._logln(f"Профиль загружен: {path} (vjoy_target={self.vjoy_target})")

    def start_feed(self) -> None:
        if not self.correction:
            mbox.showinfo("Нет профиля", "Сначала «Замерить покой» или «Загрузить JSON».")
            return
        if self._feed_running:
            return
        try:
            import pyvjoy
        except ImportError:
            mbox.showerror("pyvjoy не установлен", "Для preview-коррекции нужен pyvjoy. Для постоянной работы используй vjoy_feeder.py.")
            return
        try:
            self._pyvjoy_dev = pyvjoy.VJoyDevice(self.vjoy_target)
        except Exception as exc:
            mbox.showerror("vJoy", f"Не удалось открыть vJoy #{self.vjoy_target}: {exc}")
            return
        self._feed_running = True
        self._logln(f"Preview-коррекция запущена → vJoy #{self.vjoy_target} (без POV).")
        threading.Thread(target=self._feed_loop, daemon=True).start()

    def stop_feed(self) -> None:
        self._feed_running = False
        self._logln("Preview-коррекция остановлена.")

    def _feed_loop(self) -> None:
        import pyvjoy
        usage = {"X": pyvjoy.HID_USAGE_X, "Y": pyvjoy.HID_USAGE_Y, "Z": pyvjoy.HID_USAGE_Z, "RX": pyvjoy.HID_USAGE_RX, "RY": pyvjoy.HID_USAGE_RY, "RZ": pyvjoy.HID_USAGE_RZ}
        delay = 1.0 / SAMPLE_HZ
        while self._feed_running and self.joy_id is not None and self.caps is not None:
            info = read_raw(self.joy_id)
            if info is not None:
                for axis in AXES:
                    fixed = apply_profile_axis(norm_axis(info, self.caps, axis), self.correction.get(axis))
                    self._pyvjoy_dev.set_axis(usage[VJOY_AXIS_MAP[axis]], to_vjoy(fixed))
                for button in range(min(32, int(self.caps.wNumButtons))):
                    self._pyvjoy_dev.set_button(button + 1, bool(info.dwButtons & (1 << button)))
            time.sleep(delay)

    def _live_loop(self) -> None:
        if self.joy_id is not None and self.caps is not None and not self.busy:
            info = read_raw(self.joy_id)
            if info is not None:
                for axis in AXES:
                    raw = norm_axis(info, self.caps, axis)
                    fixed = apply_profile_axis(raw, self.correction.get(axis)) if self.correction else raw
                    self._draw_axis(axis, raw, fixed)
                    self.axis_lbl[axis].set(f"raw={raw:+.4f}   corr={fixed:+.4f}")
                buttons = [str(button + 1) for button in range(min(32, int(self.caps.wNumButtons))) if info.dwButtons & (1 << button)]
                pov = "центр" if info.dwPOV == JOY_POVCENTERED else f"{info.dwPOV / 100:.0f}°"
                self.btn_var.set(f"Кнопки: {' '.join(buttons) or '—'}    POV: {pov}")
        self.root.after(40, self._live_loop)

    def _draw_axis(self, axis: str, raw: float, fixed: float) -> None:
        canvas = self.axis_canvas[axis]
        canvas.delete("all")
        width = int(canvas["width"])
        height = int(canvas["height"])
        canvas.create_line(width // 2, 0, width // 2, height, fill="#ddd")
        raw_x = int((raw + 1) / 2 * width)
        fixed_x = int((fixed + 1) / 2 * width)
        canvas.create_line(raw_x, 0, raw_x, height, fill="#1a6", width=2)
        canvas.create_line(fixed_x, 0, fixed_x, height, fill="#06c", width=2)

    def _run_async(self, fn, on_done) -> None:
        def worker():
            try:
                self.result_q.put((on_done, fn()))
            except Exception as exc:
                self.result_q.put((self._on_error, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _on_error(self, message: str) -> None:
        self.busy = False
        self._logln(f"ОШИБКА: {message}")
        mbox.showerror("Ошибка", message)

    def _poll_queue(self) -> None:
        try:
            while True:
                callback, result = self.result_q.get_nowait()
                callback(result)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _logln(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")


class ReconnectTest:
    def __init__(self, parent, app: JoyDiagApp):
        self.app = app
        self.rounds: list[dict] = []
        self.jitter_rounds: list[dict] = []
        base = Path(__file__).resolve().parent
        self.log_path = base / "port_center_log.csv"
        self.jitter_log_path = base / "port_jitter_log.csv"
        self._build(parent)

    def _build(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Тест переподключения (поиск оптимального USB-порта)")
        frame.pack(fill="x", padx=8, pady=6)
        top = ttk.Frame(frame)
        top.pack(fill="x", padx=4, pady=4)
        ttk.Label(top, text="Метка порта:").pack(side="left")
        self.port_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.port_var, width=24).pack(side="left", padx=4)
        ttk.Button(top, text="Снять раунд", command=self.take_round).pack(side="left", padx=3)
        ttk.Button(top, text="Сброс таблицы", command=self.clear).pack(side="left", padx=3)
        ttk.Button(top, text="Рекомендация", command=self.recommend).pack(side="left", padx=3)

        jr = ttk.Frame(frame)
        jr.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(jr, text=f"Замер дрожания ({PORT_JITTER_SECS}с, все оси)", command=self.take_jitter).pack(side="left", padx=3)
        ttk.Button(jr, text="Рекомендация по дрожанию", command=self.recommend_jitter).pack(side="left", padx=3)
        ttk.Label(jr, text="(лог → port_jitter_log.csv)", foreground="#777").pack(side="left", padx=6)

        cols = ("n", "port", "cx", "cy", "sx", "sy", "drift", "ts")
        heads = ("№", "Метка порта", "центр X", "центр Y", "σ X", "σ Y", "max|увод|", "время")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=6)
        for col, head in zip(cols, heads):
            self.tree.heading(col, text=head)
            self.tree.column(col, width=82, anchor="center")
        self.tree.column("port", width=150, anchor="w")
        self.tree.pack(fill="x", padx=4, pady=4)

    def _port_label(self, fallback_count: int) -> str | None:
        port = self.port_var.get().strip()
        if port:
            return port
        if not mbox.askyesno("Метка порта пустая", "Снять замер без метки порта?"):
            return None
        return f"(порт #{fallback_count})"

    def take_round(self) -> None:
        if self.app.joy_id is None:
            mbox.showwarning("Нет устройства", "Сначала выбери манипулятор и обнови список.")
            return
        if self.app.busy:
            mbox.showinfo("Занято", "Идёт другой замер.")
            return
        port = self._port_label(len(self.rounds) + 1)
        if port is None:
            return
        self.app.busy = True
        self.app._logln(f"Раунд переподключения [{port}] — НЕ трогай ручку…")
        self.app._run_async(lambda: self.app.sample_rest(RECONNECT_SECS, SAMPLE_HZ, axes=["X", "Y"]), lambda data, p=port: self._on_round(p, data))

    def _on_round(self, port: str, data: dict[str, list[float]]) -> None:
        self.app.busy = False
        sx = axis_stats(data.get("X", []))
        sy = axis_stats(data.get("Y", []))
        row = dict(
            n=len(self.rounds) + 1,
            port=port,
            cx=sx["mean"],
            cy=sy["mean"],
            sx=sx["sd"],
            sy=sy["sd"],
            drift=max(abs(sx["mean"]), abs(sy["mean"])),
            ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.rounds.append(row)
        self.tree.insert("", "end", values=(row["n"], row["port"], f"{row['cx']:+.4f}", f"{row['cy']:+.4f}", f"{row['sx']:.4f}", f"{row['sy']:.4f}", f"{row['drift']:.4f}", row["ts"]))
        self._log_row(row)
        self.app._logln(f"  [{port}] центр X={row['cx']:+.4f} Y={row['cy']:+.4f} σX={row['sx']:.4f} σY={row['sy']:.4f}")

    def _log_row(self, row: dict) -> None:
        new_file = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if new_file:
                writer.writerow(["timestamp", "round", "port_label", "center_X", "center_Y", "sigma_X", "sigma_Y", "max_abs_drift"])
            writer.writerow([row["ts"], row["n"], row["port"], f"{row['cx']:.6f}", f"{row['cy']:.6f}", f"{row['sx']:.6f}", f"{row['sy']:.6f}", f"{row['drift']:.6f}"])

    def take_jitter(self) -> None:
        if self.app.joy_id is None:
            mbox.showwarning("Нет устройства", "Сначала выбери манипулятор и обнови список.")
            return
        if self.app.busy:
            mbox.showinfo("Занято", "Идёт другой замер.")
            return
        port = self._port_label(len(self.jitter_rounds) + 1)
        if port is None:
            return
        self.app.busy = True
        self.app._logln(f"Замер дрожания [{port}] {PORT_JITTER_SECS}с (все 6 осей) — НЕ трогай ручку…")
        self.app._run_async(lambda: self.app.sample_rest(PORT_JITTER_SECS, SAMPLE_HZ, axes=AXES), lambda data, p=port: self._on_jitter(p, data))

    def _on_jitter(self, port: str, data: dict[str, list[float]]) -> None:
        self.app.busy = False
        per = {axis: axis_stats(data.get(axis, [])) for axis in AXES}
        row = dict(ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), port=port, secs=PORT_JITTER_SECS, per=per)
        self.jitter_rounds.append(row)
        self._log_jitter_row(row)
        worst = max(AXES, key=lambda axis: per[axis]["sd"])
        lines = [f"Дрожание [{port}] {PORT_JITTER_SECS}с (все оси):"]
        for axis in AXES:
            st = per[axis]
            lines.append(f"  {axis}: σ={st['sd']:.4f}  p2p={st['spread']:.4f}  drift={st['drift']:+.4f}  center={st['mean']:+.4f}")
        lines.append(f"Худшая ось по шуму: {worst} (σ={per[worst]['sd']:.4f})")
        text = "\n".join(lines)
        self.app._logln(text)
        mbox.showinfo("Замер дрожания", text)

    def _log_jitter_row(self, row: dict) -> None:
        new_file = not self.jitter_log_path.exists()
        with self.jitter_log_path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if new_file:
                head = ["timestamp", "port_label", "duration_s"]
                for axis in AXES:
                    head += [f"center_{axis}", f"sigma_{axis}", f"p2p_{axis}", f"drift_{axis}"]
                writer.writerow(head)
            vals = [row["ts"], row["port"], f"{row['secs']:.1f}"]
            for axis in AXES:
                st = row["per"][axis]
                vals += [f"{st['mean']:.6f}", f"{st['sd']:.6f}", f"{st['spread']:.6f}", f"{st['drift']:.6f}"]
            writer.writerow(vals)

    def clear(self) -> None:
        if self.rounds and not mbox.askyesno("Сброс", "Очистить таблицу? (лог-файл останется)"):
            return
        self.rounds.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

    def recommend(self) -> None:
        if len(self.rounds) < 2:
            mbox.showinfo("Рекомендация", "Сними хотя бы 2-3 раунда на разных портах.")
            return
        by_port = {}
        for row in self.rounds:
            by_port.setdefault(row["port"], []).append(row)
        scored = []
        for port, rows in by_port.items():
            drift = sum(row["drift"] for row in rows) / len(rows)
            noise = sum((row["sx"] + row["sy"]) / 2 for row in rows) / len(rows)
            cxs = [row["cx"] for row in rows]
            cys = [row["cy"] for row in rows]
            spread = max(max(cxs) - min(cxs), max(cys) - min(cys)) if len(rows) > 1 else 0.0
            scored.append((drift + noise + spread, port, drift, noise, spread, len(rows)))
        scored.sort()
        lines = ["Рейтинг портов (меньше = лучше):", ""]
        for idx, (_score, port, drift, noise, spread, count) in enumerate(scored, 1):
            mark = "   ← ОПТИМАЛЬНЫЙ" if idx == 1 else ""
            lines.append(f"{idx}. {port}{mark}")
            lines.append(f"     увод={drift:.4f}  шум={noise:.4f}  разброс={spread:.4f}  (раундов: {count})")
        self._show_and_log_summary("Рекомендация по портам", lines, self.log_path.with_name("port_center_log_summary.txt"))

    def recommend_jitter(self) -> None:
        if len(self.jitter_rounds) < 2:
            mbox.showinfo("Рекомендация по дрожанию", "Сними замеры дрожания хотя бы на 2 портах.")
            return
        by_port = {}
        for row in self.jitter_rounds:
            by_port.setdefault(row["port"], []).append(row)
        scored = []
        for port, rows in by_port.items():
            sigmas, p2ps = [], []
            for row in rows:
                for axis in AXES:
                    sigmas.append(row["per"][axis]["sd"])
                    p2ps.append(row["per"][axis]["spread"])
            mean_sigma = sum(sigmas) / len(sigmas)
            mean_p2p = sum(p2ps) / len(p2ps)
            scored.append((mean_sigma + mean_p2p, port, mean_sigma, mean_p2p, len(rows)))
        scored.sort()
        lines = ["Рейтинг портов по дрожанию (меньше = тише):", ""]
        for idx, (_score, port, sigma, p2p, count) in enumerate(scored, 1):
            mark = "   ← САМЫЙ ТИХИЙ" if idx == 1 else ""
            lines.append(f"{idx}. {port}{mark}")
            lines.append(f"     ср.σ={sigma:.4f}  ср.p2p={p2p:.4f}  (замеров: {count})")
        self._show_and_log_summary("Рекомендация по дрожанию", lines, self.jitter_log_path.with_name("port_jitter_log_summary.txt"))

    def _show_and_log_summary(self, title: str, lines: list[str], path: Path) -> None:
        text = "\n".join(lines)
        mbox.showinfo(title, text)
        self.app._logln(text)
        with path.open("a", encoding="utf-8") as file:
            file.write(f"\n=== {title} {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
            file.write(text + "\n")


def main() -> None:
    if not require_windows():
        print("JoyDiag использует winmm.dll и работает только на Windows.")
        return
    root = tk.Tk()
    JoyDiagApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
