# -*- coding: utf-8 -*-
"""
JoyDiag 2.0 — диагностика манипуляторов и подготовка профиля коррекции осей для vJoy.
Speedlink Black Widow SL-6640 (VID 0x07B5 / PID 0x0317) и любые другие джойстики.

Возможности:
  - поиск ВСЕХ манипуляторов (id 0..15), VID/PID, оси/кнопки/POV;
  - живой просмотр осей X/Y/Z/R/U/V, кнопок, POV (сырое + с коррекцией);
  - диагностика покоя (8с): центр/шум/σ/дрейф/deadzone;
  - калибровка краёв (12с): реальные min/max;
  - автогенерация профиля коррекции, выгрузка JSON + CSV, загрузка JSON;
  - запуск коррекции прямо из GUI через pyvjoy (опционально, БЕЗ POV);
  - ДИАГНОСТИКА ЖЕЛЕЗА «почему уводит»:
        * Тест дрожания (60с);
        * Тест переподключения (метка порта + лог + рекомендация оптимального USB-порта);
        * Замер дрожания по USB-порту (60с, все 6 осей,
          лог port_jitter_log.csv + рекомендация самого тихого порта);
        * Калибровка Windows (чтение реестра);
        * Сброс калибровки Windows (удаление ветки HKCU).

Совместимость:
  - Только Windows: чтение через системный winmm (joyGetPosEx); на Linux/Mac не работает.
  - Диагностика работает БЕЗ зависимостей на любой Windows-машине для устройств,
    видимых как game controller (joy.cpl): джойстики, флайт-стики, штурвалы, РУД, педали.
  - Лимиты идут от самого winmm: до 16 устройств (id 0..15), до 6 осей (X/Y/Z/R/U/V),
    до 32 кнопок + 1 POV на устройство.
  - НЕ покрывает: Xbox/XInput-геймпады (оба триггера делят ось Z, нет раздельных LT/RT),
    устройства с >6 осями или >32 кнопками, чистый raw-HID без регистрации в game
    controllers. Снятие этих лимитов — только переход чтения на DirectInput/raw HID.
  - Коррекция (профиль + vjoy_feeder.py) завязана на конкретное железо и требует vJoy
    (опц. HidHide) — это уже не «любой ПК без настройки».

Зависимости: стандартная библиотека + (опц.) pyvjoy для встроенной коррекции.
"""

import os
import csv
import time
import json
import queue
import ctypes
import threading
import statistics
import datetime
from ctypes import wintypes

import tkinter as tk
from tkinter import ttk, filedialog
import tkinter.messagebox as mbox

try:
    import winreg
except ImportError:
    winreg = None

# ------------------------------------------------------------------ winmm ----

winmm = ctypes.windll.winmm

JOYERR_NOERROR = 0
JOY_RETURNALL = 0x000000FF
JOY_POVCENTERED = 0xFFFF
MAXPNAMELEN = 32
MAX_JOYSTICKOEMVXD = 260

AXES = ["X", "Y", "Z", "R", "U", "V"]
SAMPLE_HZ = 100
REST_SECONDS = 8
EDGE_SECONDS = 12
JITTER_SECONDS = 60
RECONNECT_SECS = 1.5
PORT_JITTER_SECS = 60   # длительность замера дрожания по порту по умолчанию

VMIN, VMAX = 1, 32768   # диапазон оси vJoy

# целевое устройство по умолчанию (для кнопок калибровки Windows)
DEFAULT_VID = 0x07B5
DEFAULT_PID = 0x0317


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

# маппинг осей в vJoy (для встроенной коррекции через pyvjoy)
VJOY_AXIS_MAP = {"X": "X", "Y": "Y", "Z": "Z", "R": "RX", "U": "RY", "V": "RZ"}


def get_caps(joy_id):
    caps = JOYCAPS()
    if winmm.joyGetDevCapsA(joy_id, ctypes.byref(caps), ctypes.sizeof(JOYCAPS)) != JOYERR_NOERROR:
        return None
    return caps


def read_raw(joy_id):
    info = JOYINFOEX()
    info.dwSize = ctypes.sizeof(JOYINFOEX)
    info.dwFlags = JOY_RETURNALL
    if winmm.joyGetPosEx(joy_id, ctypes.byref(info)) != JOYERR_NOERROR:
        return None
    return info


def norm_axis(info, caps, ax):
    posf, minf, maxf = AXIS_FIELDS[ax]
    raw = getattr(info, posf)
    lo = getattr(caps, minf)
    hi = getattr(caps, maxf)
    if hi <= lo:
        return 0.0
    return (raw - lo) / (hi - lo) * 2.0 - 1.0


def device_name(caps):
    try:
        return caps.szPname.decode("cp1251", errors="replace").strip("\x00").strip()
    except Exception:
        return "Joystick"


def device_vidpid(caps):
    return caps.wMid, caps.wPid


def enumerate_devices():
    """Список (joy_id, caps) реально подключённых устройств."""
    found = []
    n = max(16, winmm.joyGetNumDevs())
    for jid in range(n):
        if read_raw(jid) is None:
            continue
        caps = get_caps(jid)
        if caps is None:
            continue
        found.append((jid, caps))
    return found


# ----------------------------------------------------------- математика ------

def axis_stats(vals):
    if not vals:
        return dict(mean=0.0, minv=0.0, maxv=0.0, spread=0.0, sd=0.0, drift=0.0)
    mean = sum(vals) / len(vals)
    mn, mx = min(vals), max(vals)
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    k = max(1, len(vals) // 10)
    drift = (sum(vals[-k:]) / k) - (sum(vals[:k]) / k)
    return dict(mean=mean, minv=mn, maxv=mx, spread=mx - mn, sd=sd, drift=drift)


def autogen_correction(st):
    """Профиль коррекции одной оси из статистики покоя."""
    mean, spread, sd = st["mean"], st["spread"], st["sd"]
    if abs(mean) > 0.9 and spread < 0.02:
        return {"type": "throttle", "center_offset": 0.0, "deadzone": 0.0,
                "scale_pos": 1.0, "scale_neg": 1.0, "invert": False}
    c = -mean                       # center_offset
    pos_reach = 1.0 + c
    neg_reach = 1.0 - c
    scale_pos = (1.0 / pos_reach) if pos_reach > 0.05 else 1.0
    scale_neg = (1.0 / neg_reach) if neg_reach > 0.05 else 1.0
    dz = spread / 2.0 + 2.0 * sd + 0.005
    return {"type": "stick", "center_offset": c, "deadzone": dz,
            "scale_pos": scale_pos, "scale_neg": scale_neg, "invert": False}


def apply_correction(norm, c):
    """Та же формула, что в vjoy_feeder.py."""
    if not c or c.get("type") == "throttle":
        v = norm
        if c and c.get("invert"):
            v = -v
        return max(-1.0, min(1.0, v))
    x = norm + c.get("center_offset", 0.0)
    dz = c.get("deadzone", 0.0)
    if dz > 0 and abs(x) <= dz:
        x = 0.0
    elif dz > 0:
        x = (abs(x) - dz) / (1.0 - dz) * (1.0 if x > 0 else -1.0)
    scale = c.get("scale_pos", 1.0) if x >= 0 else c.get("scale_neg", 1.0)
    x *= scale
    x = max(-1.0, min(1.0, x))
    if c.get("invert"):
        x = -x
    return x


def to_vjoy(fixed):
    return int(round((fixed + 1.0) / 2.0 * (VMAX - VMIN) + VMIN))


# ---------------------------------------------------- реестр (Windows cal) ---

JOY_OEM = r"System\CurrentControlSet\Control\MediaProperties\PrivateProperties\Joystick\OEM"
DINPUT = r"System\CurrentControlSet\Control\MediaProperties\PrivateProperties\DirectInput"


def _dev_key(vid, pid):
    return f"VID_{vid:04X}&PID_{pid:04X}"


def _reg_hives():
    return [("HKCU", winreg.HKEY_CURRENT_USER),
            ("HKLM", winreg.HKEY_LOCAL_MACHINE)]


def _reg_targets(vid, pid):
    dev = _dev_key(vid, pid)
    return [("Joystick/OEM (winmm)", f"{JOY_OEM}\\{dev}"),
            ("DirectInput", f"{DINPUT}\\{dev}")]


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
        k = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except FileNotFoundError:
        return None
    names, i = [], 0
    while True:
        try:
            names.append(winreg.EnumKey(k, i))
        except OSError:
            break
        i += 1
    winreg.CloseKey(k)
    return names


def find_windows_calibration(vid, pid):
    found = []
    for hname, hive in _reg_hives():
        for label, path in _reg_targets(vid, pid):
            try:
                k = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            except FileNotFoundError:
                continue
            except PermissionError:
                found.append(dict(hive=hname, label=label, path=path,
                                  status="нет доступа", values={}))
                continue
            vals = _enum_values(k)
            winreg.CloseKey(k)
            found.append(dict(hive=hname, label=label, path=path,
                              status="ЕСТЬ", values=vals))
    return found


def _delete_tree(hive, path):
    subs = _subkeys(hive, path)
    if subs is None:
        return False
    for s in subs:
        _delete_tree(hive, f"{path}\\{s}")
    winreg.DeleteKeyEx(hive, path, winreg.KEY_WOW64_64KEY, 0)
    return True


def delete_windows_calibration(vid, pid, include_hklm=False):
    deleted, errors = [], []
    hives = _reg_hives() if include_hklm else _reg_hives()[:1]
    for hname, hive in hives:
        for _, path in _reg_targets(vid, pid):
            try:
                if _delete_tree(hive, path):
                    deleted.append(f"{hname}\\{path}")
            except PermissionError:
                errors.append(f"{hname}\\{path} — нужны права администратора")
            except FileNotFoundError:
                pass
    return deleted, errors


# ===================================================================== GUI ===

class JoyDiagApp:
    def __init__(self, root):
        self.root = root
        root.title("JoyDiag 2.0 — диагностика и коррекция осей")
        root.geometry("980x860")

        self.devices = []          # [(joy_id, caps)]
        self.joy_id = None
        self.caps = None

        self.correction = {}       # {axis: corr_dict}
        self.ranges = {}           # {axis: (min,max)} из калибровки краёв
        self.last_rest = {}        # {axis: stats}
        self.vjoy_target = 1

        self.busy = False
        self.result_q = queue.Queue()

        self._pyvjoy_dev = None
        self._feed_running = False

        self._build_ui()
        self.refresh_devices()
        self.root.after(50, self._poll_queue)
        self.root.after(40, self._live_loop)

    # ----------------------------------------------------------- построение --

    def _build_ui(self):
        # верх: выбор устройства
        top = ttk.Frame(self.root); top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Устройство:").pack(side="left")
        self.dev_var = tk.StringVar()
        self.dev_combo = ttk.Combobox(top, textvariable=self.dev_var, width=58, state="readonly")
        self.dev_combo.pack(side="left", padx=4)
        self.dev_combo.bind("<<ComboboxSelected>>", lambda e: self._select_device())
        ttk.Button(top, text="Обновить", command=self.refresh_devices).pack(side="left", padx=4)
        self.info_var = tk.StringVar(value="—")
        ttk.Label(self.root, textvariable=self.info_var, foreground="#555").pack(fill="x", padx=10)

        # живой просмотр осей
        live = ttk.LabelFrame(self.root, text="Живой просмотр (сырое → с коррекцией)")
        live.pack(fill="x", padx=8, pady=6)
        self.axis_canvas = {}
        self.axis_lbl = {}
        for ax in AXES:
            row = ttk.Frame(live); row.pack(fill="x", padx=6, pady=1)
            ttk.Label(row, text=ax, width=3).pack(side="left")
            cv = tk.Canvas(row, width=420, height=18, bg="white", highlightthickness=1,
                           highlightbackground="#ccc")
            cv.pack(side="left", padx=4)
            self.axis_canvas[ax] = cv
            lbl = tk.StringVar(value="—")
            ttk.Label(row, textvariable=lbl, width=42, font=("Consolas", 9)).pack(side="left")
            self.axis_lbl[ax] = lbl
        self.btn_var = tk.StringVar(value="Кнопки: —    POV: —")
        ttk.Label(live, textvariable=self.btn_var, font=("Consolas", 9)).pack(fill="x", padx=8, pady=3)

        # диагностика
        diag = ttk.LabelFrame(self.root, text="Диагностика и профиль")
        diag.pack(fill="x", padx=8, pady=6)
        r1 = ttk.Frame(diag); r1.pack(fill="x", padx=4, pady=3)
        ttk.Button(r1, text=f"Замерить покой ({REST_SECONDS}с)",
                   command=self.measure_rest).pack(side="left", padx=3)
        ttk.Button(r1, text=f"Калибровка краёв ({EDGE_SECONDS}с)",
                   command=self.measure_edges).pack(side="left", padx=3)
        ttk.Button(r1, text="Сохр. JSON", command=self.save_json).pack(side="left", padx=3)
        ttk.Button(r1, text="Сохр. CSV", command=self.save_csv).pack(side="left", padx=3)
        ttk.Button(r1, text="Загрузить JSON", command=self.load_json).pack(side="left", padx=3)
        r2 = ttk.Frame(diag); r2.pack(fill="x", padx=4, pady=3)
        ttk.Button(r2, text="Запуск коррекции (pyvjoy)", command=self.start_feed).pack(side="left", padx=3)
        ttk.Button(r2, text="Стоп", command=self.stop_feed).pack(side="left", padx=3)
        ttk.Label(r2, text="(встроенная коррекция БЕЗ POV — для боя используй vjoy_feeder.py)",
                  foreground="#a00").pack(side="left", padx=6)

        # диагностика железа
        hw = ttk.LabelFrame(self.root, text="Диагностика железа «почему уводит»")
        hw.pack(fill="x", padx=8, pady=6)
        hr = ttk.Frame(hw); hr.pack(fill="x", padx=4, pady=3)
        ttk.Button(hr, text=f"Тест дрожания ({JITTER_SECONDS}с)",
                   command=self.jitter_test).pack(side="left", padx=3)
        ttk.Button(hr, text="Калибровка Windows (чтение)",
                   command=self.read_windows_cal).pack(side="left", padx=3)
        ttk.Button(hr, text="Сбросить калибровку Windows",
                   command=self.reset_windows_cal).pack(side="left", padx=3)

        # тест переподключения / порты
        self.reconnect = ReconnectTest(self.root, self)

        # лог
        logf = ttk.LabelFrame(self.root, text="Журнал")
        logf.pack(fill="both", expand=True, padx=8, pady=6)
        self.log = tk.Text(logf, height=8, font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    # --------------------------------------------------------- устройства ----

    def refresh_devices(self):
        self.devices = enumerate_devices()
        items = []
        for jid, caps in self.devices:
            vid, pid = device_vidpid(caps)
            items.append(f"[{jid}] {device_name(caps)}  VID_{vid:04X}&PID_{pid:04X}")
        self.dev_combo["values"] = items
        if items:
            self.dev_combo.current(0)
            self._select_device()
        else:
            self.info_var.set("Манипуляторы не найдены")
        self._logln(f"Найдено устройств: {len(items)}")

    def _select_device(self):
        idx = self.dev_combo.current()
        if idx < 0 or idx >= len(self.devices):
            return
        self.joy_id, self.caps = self.devices[idx]
        vid, pid = device_vidpid(self.caps)
        self.info_var.set(
            f"id {self.joy_id} · {device_name(self.caps)} · VID_{vid:04X}&PID_{pid:04X} · "
            f"осей {self.caps.wNumAxes} · кнопок {self.caps.wNumButtons} · "
            f"POV {'есть' if self.caps.wCaps else 'нет'}")

    def current_vidpid(self):
        if self.caps is not None:
            return device_vidpid(self.caps)
        return DEFAULT_VID, DEFAULT_PID

    # --------------------------------------------------------- сэмплер -------

    def sample_rest(self, secs, hz, axes=None):
        """Возвращает {axis: [norm_values]} за secs секунд. Блокирующий — звать в потоке."""
        axes = axes or AXES
        data = {ax: [] for ax in axes}
        if self.joy_id is None:
            return data
        n = int(secs * hz)
        dt = 1.0 / hz
        for _ in range(n):
            info = read_raw(self.joy_id)
            if info is not None:
                for ax in axes:
                    data[ax].append(norm_axis(info, self.caps, ax))
            time.sleep(dt)
        return data

    # --------------------------------------------------------- замеры --------

    def _guard(self):
        if self.joy_id is None:
            mbox.showwarning("Нет устройства", "Сначала выбери манипулятор.")
            return False
        if self.busy:
            mbox.showinfo("Занято", "Уже идёт замер, дождись завершения.")
            return False
        return True

    def measure_rest(self):
        if not self._guard():
            return
        self.busy = True
        self._logln(f"Замер покоя {REST_SECONDS}с — убери руки…")
        self._run_async(lambda: self.sample_rest(REST_SECONDS, SAMPLE_HZ), self._on_rest)

    def _on_rest(self, data):
        self.busy = False
        self.last_rest = {ax: axis_stats(data[ax]) for ax in AXES}
        self.correction = {ax: autogen_correction(self.last_rest[ax]) for ax in AXES}
        self._logln("Покой измерен. Профиль коррекции сгенерирован:")
        for ax in AXES:
            st = self.last_rest[ax]
            c = self.correction[ax]
            self._logln(f"  {ax}: center={st['mean']:+.4f} σ={st['sd']:.4f} "
                        f"spread={st['spread']:.4f} drift={st['drift']:+.4f} → "
                        f"{c['type']} off={c['center_offset']:+.4f} dz={c['deadzone']:.4f} "
                        f"sp={c['scale_pos']:.3f} sn={c['scale_neg']:.3f}")

    def measure_edges(self):
        if not self._guard():
            return
        self.busy = True
        self._logln(f"Калибровка краёв {EDGE_SECONDS}с — гоняй ВСЕ оси до упоров…")
        self._run_async(lambda: self.sample_rest(EDGE_SECONDS, SAMPLE_HZ), self._on_edges)

    def _on_edges(self, data):
        self.busy = False
        for ax in AXES:
            vals = data[ax]
            if not vals:
                continue
            mn, mx = min(vals), max(vals)
            if (mx - mn) * (VMAX - VMIN) / 2.0 < 8:   # игнор «мёртвой» оси
                continue
            self.ranges[ax] = (mn, mx)
        self._logln("Калибровка краёв завершена: " +
                    (", ".join(f"{ax}[{self.ranges[ax][0]:+.2f}..{self.ranges[ax][1]:+.2f}]"
                              for ax in self.ranges) or "(оси не двигали)"))

    def jitter_test(self):
        if not self._guard():
            return
        self.busy = True
        self._logln(f"Тест дрожания {JITTER_SECONDS}с — НЕ трогай ручку…")
        self._run_async(lambda: self.sample_rest(JITTER_SECONDS, SAMPLE_HZ), self._on_jitter)

    def _on_jitter(self, data):
        self.busy = False
        self._logln("=== Тест дрожания: интерпретация ===")
        for ax in ("X", "Y", "R"):
            st = axis_stats(data[ax])
            verdict = self._jitter_verdict(st)
            self._logln(f"  {ax}: σ={st['sd']:.4f} spread={st['spread']:.4f} "
                        f"drift={st['drift']:+.4f}  → {verdict}")

    @staticmethod
    def _jitter_verdict(st):
        if st["sd"] > 0.02 or st["spread"] > 0.08:
            return "высокий шум → износ/грязь потенциометра (чистка/замена)"
        if abs(st["drift"]) > 0.03:
            return "дрейф во времени → проседание USB-питания (убрать хаб, другой порт)"
        if abs(st["mean"]) > 0.02:
            return "стабильный увод при малом шуме → лечится center_offset (механика/калибровка)"
        return "ось стабильна — увод не обнаружен"

    # --------------------------------------------------- калибровка Windows --

    def read_windows_cal(self):
        if winreg is None:
            mbox.showerror("Реестр", "Модуль winreg недоступен (не Windows?).")
            return
        vid, pid = self.current_vidpid()
        found = [f for f in find_windows_calibration(vid, pid) if f["status"] == "ЕСТЬ"]
        if not found:
            mbox.showinfo("Калибровка Windows",
                          f"Сохранённой калибровки Windows для VID_{vid:04X}&PID_{pid:04X} "
                          f"не найдено.\nЗначит увод — чисто железный.")
            self._logln("Калибровка Windows: НЕ найдена (увод железный).")
            return
        lines = []
        for f in found:
            lines.append(f"[{f['hive']}] {f['label']}\n    {f['path']}")
            for name, val in f["values"].items():
                sval = val if isinstance(val, str) else f"<{type(val).__name__}, {len(val) if hasattr(val,'__len__') else ''} б>"
                lines.append(f"      {name} = {sval}")
        mbox.showinfo("Калибровка Windows найдена", "\n".join(lines))
        self._logln("Калибровка Windows: НАЙДЕНА\n" + "\n".join(lines))

    def reset_windows_cal(self):
        if winreg is None:
            mbox.showerror("Реестр", "Модуль winreg недоступен (не Windows?).")
            return
        vid, pid = self.current_vidpid()
        found = [f for f in find_windows_calibration(vid, pid) if f["status"] == "ЕСТЬ"]
        if not found:
            mbox.showinfo("Сброс калибровки", "Сохранённой калибровки Windows нет — сбрасывать нечего.")
            return
        paths = "\n".join(f"• {f['hive']}: {f['path']}" for f in found)
        if not mbox.askyesno("Сбросить калибровку Windows?",
                             "Будут удалены пользовательские ветки калибровки:\n\n" + paths +
                             "\n\nWindows пересоздаст дефолт при следующем подключении.\n"
                             "Удалять? (HKLM — только с правами админа)"):
            return
        deleted, errors = delete_windows_calibration(vid, pid, include_hklm=False)
        msg = ""
        if deleted:
            msg += "Удалено:\n" + "\n".join(deleted)
        if errors:
            msg += "\n\nНе удалено:\n" + "\n".join(errors)
        msg += "\n\nПЕРЕПОДКЛЮЧИ USB (вынь/вставь), чтобы Windows взяла дефолт."
        mbox.showinfo("Готово", msg)
        self._logln("Сброс калибровки Windows:\n" + msg)

    # --------------------------------------------------- профиль JSON/CSV ----

    def _build_profile(self):
        vid, pid = self.current_vidpid()
        axes_out = {}
        for ax in AXES:
            c = dict(self.correction.get(ax, autogen_correction(
                self.last_rest.get(ax, axis_stats([])))))
            if ax in self.ranges:
                c["calibrated_min"], c["calibrated_max"] = self.ranges[ax]
            axes_out[ax] = c
        return {
            "device": {"name": device_name(self.caps) if self.caps else "",
                       "vid": f"0x{vid:04X}", "pid": f"0x{pid:04X}",
                       "joy_id": self.joy_id},
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "vjoy_target": self.vjoy_target,
            "correction": axes_out,
        }

    def save_json(self):
        if not self.correction:
            mbox.showinfo("Нет профиля", "Сначала «Замерить покой».")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            initialfile="joydiag_profile_final.json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._build_profile(), f, ensure_ascii=False, indent=2)
        self._logln(f"Профиль сохранён: {path}")

    def save_csv(self):
        if not self.last_rest:
            mbox.showinfo("Нет данных", "Сначала «Замерить покой».")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile="joydiag_rest.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["axis", "mean", "min", "max", "spread", "sigma", "drift"])
            for ax in AXES:
                st = self.last_rest.get(ax, axis_stats([]))
                w.writerow([ax, f"{st['mean']:.6f}", f"{st['minv']:.6f}", f"{st['maxv']:.6f}",
                            f"{st['spread']:.6f}", f"{st['sd']:.6f}", f"{st['drift']:.6f}"])
        self._logln(f"CSV сохранён: {path}")

    def load_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            prof = json.load(f)
        self.correction = prof.get("correction", {})
        self.vjoy_target = prof.get("vjoy_target", 1)
        for ax, c in self.correction.items():
            if "calibrated_min" in c and "calibrated_max" in c:
                self.ranges[ax] = (c["calibrated_min"], c["calibrated_max"])
        self._logln(f"Профиль загружен: {path} (vjoy_target={self.vjoy_target})")

    # ---------------------------------------------- встроенная коррекция -----

    def start_feed(self):
        if not self.correction:
            mbox.showinfo("Нет профиля", "Сначала «Замерить покой» или «Загрузить JSON».")
            return
        if self._feed_running:
            return
        try:
            import pyvjoy
        except ImportError:
            mbox.showerror("pyvjoy не установлен",
                           "Для встроенной коррекции нужен pyvjoy:\n  pip install pyvjoy\n"
                           "и установленный драйвер vJoy.\n\n"
                           "Для постоянной работы используй vjoy_feeder.py (он без pyvjoy и с POV).")
            return
        try:
            self._pyvjoy_dev = pyvjoy.VJoyDevice(self.vjoy_target)
        except Exception as e:
            mbox.showerror("vJoy", f"Не удалось открыть vJoy #{self.vjoy_target}: {e}")
            return
        self._feed_running = True
        self._logln(f"Коррекция запущена → vJoy #{self.vjoy_target} (без POV).")
        threading.Thread(target=self._feed_loop, daemon=True).start()

    def stop_feed(self):
        self._feed_running = False
        self._logln("Коррекция остановлена.")

    def _feed_loop(self):
        import pyvjoy
        usage = {
            "X": pyvjoy.HID_USAGE_X, "Y": pyvjoy.HID_USAGE_Y, "Z": pyvjoy.HID_USAGE_Z,
            "RX": pyvjoy.HID_USAGE_RX, "RY": pyvjoy.HID_USAGE_RY, "RZ": pyvjoy.HID_USAGE_RZ,
        }
        dt = 1.0 / SAMPLE_HZ
        while self._feed_running and self.joy_id is not None:
            info = read_raw(self.joy_id)
            if info is not None:
                for ax in AXES:
                    fixed = apply_correction(norm_axis(info, self.caps, ax),
                                             self.correction.get(ax))
                    self._pyvjoy_dev.set_axis(usage[VJOY_AXIS_MAP[ax]], to_vjoy(fixed))
                for b in range(min(32, self.caps.wNumButtons)):
                    self._pyvjoy_dev.set_button(b + 1, bool(info.dwButtons & (1 << b)))
            time.sleep(dt)

    # ---------------------------------------------------- живой просмотр -----

    def _live_loop(self):
        if self.joy_id is not None and not self.busy:
            info = read_raw(self.joy_id)
            if info is not None:
                for ax in AXES:
                    raw = norm_axis(info, self.caps, ax)
                    fixed = apply_correction(raw, self.correction.get(ax)) if self.correction else raw
                    self._draw_axis(ax, raw, fixed)
                    self.axis_lbl[ax].set(f"raw={raw:+.4f}   corr={fixed:+.4f}")
                btns = [str(b + 1) for b in range(min(32, self.caps.wNumButtons))
                        if info.dwButtons & (1 << b)]
                pov = "центр" if info.dwPOV == JOY_POVCENTERED else f"{info.dwPOV / 100:.0f}°"
                self.btn_var.set(f"Кнопки: {' '.join(btns) or '—'}    POV: {pov}")
        self.root.after(40, self._live_loop)

    def _draw_axis(self, ax, raw, fixed):
        cv = self.axis_canvas[ax]
        cv.delete("all")
        w = int(cv["width"]); h = int(cv["height"])
        cv.create_line(w // 2, 0, w // 2, h, fill="#ddd")
        xr = int((raw + 1) / 2 * w)
        xf = int((fixed + 1) / 2 * w)
        cv.create_line(xr, 0, xr, h, fill="#1a6", width=2)      # сырое
        cv.create_line(xf, 0, xf, h, fill="#06c", width=2)      # коррекция

    # ---------------------------------------------------------- утилиты ------

    def _run_async(self, fn, on_done):
        def worker():
            try:
                res = fn()
                self.result_q.put((on_done, res))
            except Exception as e:
                self.result_q.put((self._on_error, str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def _on_error(self, msg):
        self.busy = False
        self._logln(f"ОШИБКА: {msg}")
        mbox.showerror("Ошибка", msg)

    def _poll_queue(self):
        try:
            while True:
                cb, res = self.result_q.get_nowait()
                cb(res)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _logln(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")


# -------------------------------------------- тест переподключения / порты ---

class ReconnectTest:
    """Тест переподключения с привязкой к USB-порту, логом и рекомендацией.

    Дополнительно: длительный замер дрожания по порту (все 6 осей) с записью
    в port_jitter_log.csv и рекомендацией самого тихого порта.
    """

    def __init__(self, parent, app):
        self.app = app
        self.rounds = []
        self.jitter_rounds = []
        base = os.path.dirname(os.path.abspath(__file__))
        self.log_path = os.path.join(base, "port_center_log.csv")
        self.jitter_log_path = os.path.join(base, "port_jitter_log.csv")
        self._build(parent)

    def _build(self, parent):
        frame = ttk.LabelFrame(parent, text="Тест переподключения (поиск оптимального USB-порта)")
        frame.pack(fill="x", padx=8, pady=6)

        top = ttk.Frame(frame); top.pack(fill="x", padx=4, pady=4)
        ttk.Label(top, text="Метка порта:").pack(side="left")
        self.port_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.port_var, width=24).pack(side="left", padx=4)
        ttk.Button(top, text="Снять раунд", command=self.take_round).pack(side="left", padx=3)
        ttk.Button(top, text="Сброс таблицы", command=self.clear).pack(side="left", padx=3)
        ttk.Button(top, text="Рекомендация", command=self.recommend).pack(side="left", padx=3)

        # длительный замер дрожания по порту (все оси)
        jr = ttk.Frame(frame); jr.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(jr, text=f"Замер дрожания ({PORT_JITTER_SECS}с, все оси)",
                   command=self.take_jitter).pack(side="left", padx=3)
        ttk.Button(jr, text="Рекомендация по дрожанию",
                   command=self.recommend_jitter).pack(side="left", padx=3)
        ttk.Label(jr, text="(лог → port_jitter_log.csv)", foreground="#777").pack(side="left", padx=6)

        cols = ("n", "port", "cx", "cy", "sx", "sy", "drift", "ts")
        heads = ("№", "Метка порта", "центр X", "центр Y", "σ X", "σ Y", "max|увод|", "время")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=6)
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=82, anchor="center")
        self.tree.column("port", width=150, anchor="w")
        self.tree.pack(fill="x", padx=4, pady=4)

    def take_round(self):
        if self.app.joy_id is None:
            mbox.showwarning("Нет устройства", "Сначала выбери манипулятор и обнови список.")
            return
        if self.app.busy:
            mbox.showinfo("Занято", "Идёт другой замер.")
            return
        port = self.port_var.get().strip()
        if not port:
            if not mbox.askyesno("Метка порта пустая", "Снять раунд без метки порта?"):
                return
            port = f"(порт #{len(self.rounds) + 1})"

        self.app.busy = True
        self.app._logln(f"Раунд переподключения [{port}] — НЕ трогай ручку…")
        self.app._run_async(
            lambda: self.app.sample_rest(RECONNECT_SECS, SAMPLE_HZ, axes=["X", "Y"]),
            lambda data, p=port: self._on_round(p, data))

    def _on_round(self, port, data):
        self.app.busy = False
        sx = axis_stats(data.get("X", []))
        sy = axis_stats(data.get("Y", []))
        max_drift = max(abs(sx["mean"]), abs(sy["mean"]))
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = dict(n=len(self.rounds) + 1, port=port,
                   cx=sx["mean"], cy=sy["mean"], sx=sx["sd"], sy=sy["sd"],
                   drift=max_drift, ts=ts)
        self.rounds.append(row)
        self.tree.insert("", "end", values=(
            row["n"], row["port"], f"{row['cx']:+.4f}", f"{row['cy']:+.4f}",
            f"{row['sx']:.4f}", f"{row['sy']:.4f}", f"{row['drift']:.4f}", row["ts"]))
        self._log_row(row)
        self.app._logln(f"  [{port}] центр X={row['cx']:+.4f} Y={row['cy']:+.4f} "
                        f"σX={row['sx']:.4f} σY={row['sy']:.4f}")

    def _log_row(self, row):
        new = not os.path.exists(self.log_path)
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp", "round", "port_label",
                            "center_X", "center_Y", "sigma_X", "sigma_Y", "max_abs_drift"])
            w.writerow([row["ts"], row["n"], row["port"],
                        f"{row['cx']:.6f}", f"{row['cy']:.6f}",
                        f"{row['sx']:.6f}", f"{row['sy']:.6f}", f"{row['drift']:.6f}"])

    # ----------------------------------------- длительный замер дрожания -----

    def take_jitter(self):
        if self.app.joy_id is None:
            mbox.showwarning("Нет устройства", "Сначала выбери манипулятор и обнови список.")
            return
        if self.app.busy:
            mbox.showinfo("Занято", "Идёт другой замер.")
            return
        secs = PORT_JITTER_SECS
        port = self.port_var.get().strip()
        if not port:
            if not mbox.askyesno("Метка порта пустая", "Снять замер дрожания без метки порта?"):
                return
            port = f"(порт #{len(self.jitter_rounds) + 1})"

        self.app.busy = True
        self.app._logln(f"Замер дрожания [{port}] {secs:.0f}с (все 6 осей) — НЕ трогай ручку…")
        self.app._run_async(
            lambda: self.app.sample_rest(secs, SAMPLE_HZ, axes=AXES),
            lambda data, p=port, s=secs: self._on_jitter(p, s, data))

    def _on_jitter(self, port, secs, data):
        self.app.busy = False
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        per = {ax: axis_stats(data.get(ax, [])) for ax in AXES}
        row = dict(ts=ts, port=port, secs=secs, per=per)
        self.jitter_rounds.append(row)
        self._log_jitter_row(row)
        worst = max(AXES, key=lambda a: per[a]["sd"])
        lines = [f"Дрожание [{port}] {secs:.0f}с (все оси):"]
        for ax in AXES:
            st = per[ax]
            lines.append(f"  {ax}: σ={st['sd']:.4f}  p2p={st['spread']:.4f}  "
                         f"drift={st['drift']:+.4f}  center={st['mean']:+.4f}")
        lines.append(f"Худшая ось по шуму: {worst} (σ={per[worst]['sd']:.4f})")
        self.app._logln("\n".join(lines))
        mbox.showinfo("Замер дрожания", "\n".join(lines))

    def _log_jitter_row(self, row):
        new = not os.path.exists(self.jitter_log_path)
        with open(self.jitter_log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                head = ["timestamp", "port_label", "duration_s"]
                for ax in AXES:
                    head += [f"center_{ax}", f"sigma_{ax}", f"p2p_{ax}", f"drift_{ax}"]
                w.writerow(head)
            vals = [row["ts"], row["port"], f"{row['secs']:.1f}"]
            for ax in AXES:
                st = row["per"][ax]
                vals += [f"{st['mean']:.6f}", f"{st['sd']:.6f}",
                         f"{st['spread']:.6f}", f"{st['drift']:.6f}"]
            w.writerow(vals)

    def recommend_jitter(self):
        if len(self.jitter_rounds) < 2:
            mbox.showinfo("Рекомендация по дрожанию",
                          "Сними замеры дрожания хотя бы на 2 портах.")
            return
        by_port = {}
        for r in self.jitter_rounds:
            by_port.setdefault(r["port"], []).append(r)
        scored = []
        for port, rs in by_port.items():
            sigmas, p2ps = [], []
            for r in rs:
                for ax in AXES:
                    sigmas.append(r["per"][ax]["sd"])
                    p2ps.append(r["per"][ax]["spread"])
            mean_sigma = sum(sigmas) / len(sigmas)
            mean_p2p = sum(p2ps) / len(p2ps)
            scored.append((mean_sigma + mean_p2p, port, mean_sigma, mean_p2p, len(rs)))
        scored.sort()
        lines = ["Рейтинг портов по дрожанию (меньше = тише):", ""]
        for i, (score, port, ms, mp, n) in enumerate(scored, 1):
            mark = "   ← САМЫЙ ТИХИЙ" if i == 1 else ""
            lines.append(f"{i}. {port}{mark}")
            lines.append(f"     ср.σ={ms:.4f}  ср.p2p={mp:.4f}  (замеров: {n})")
        lines += ["", "Учитывались все 6 осей (σ + размах p2p)."]
        mbox.showinfo("Рекомендация по дрожанию", "\n".join(lines))
        self.app._logln("\n".join(lines))
        with open(self.jitter_log_path.replace(".csv", "_summary.txt"), "a", encoding="utf-8") as f:
            f.write(f"\n=== Дрожание {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
            f.write("\n".join(lines) + "\n")

    def clear(self):
        if self.rounds and not mbox.askyesno("Сброс", "Очистить таблицу? (лог-файл останется)"):
            return
        self.rounds.clear()
        for i in self.tree.get_children():
            self.tree.delete(i)

    def recommend(self):
        if len(self.rounds) < 2:
            mbox.showinfo("Рекомендация", "Сними хотя бы 2-3 раунда на разных портах.")
            return
        by_port = {}
        for r in self.rounds:
            by_port.setdefault(r["port"], []).append(r)

        scored = []
        for port, rs in by_port.items():
            drift = sum(x["drift"] for x in rs) / len(rs)
            noise = sum((x["sx"] + x["sy"]) / 2 for x in rs) / len(rs)
            cxs = [x["cx"] for x in rs]; cys = [x["cy"] for x in rs]
            spread = max(max(cxs) - min(cxs), max(cys) - min(cys)) if len(rs) > 1 else 0.0
            scored.append((drift + noise + spread, port, drift, noise, spread, len(rs)))
        scored.sort()

        lines = ["Рейтинг портов (меньше = лучше):", ""]
        for i, (score, port, drift, noise, spread, n) in enumerate(scored, 1):
            mark = "   ← ОПТИМАЛЬНЫЙ" if i == 1 else ""
            lines.append(f"{i}. {port}{mark}")
            lines.append(f"     увод={drift:.4f}  шум={noise:.4f}  разброс={spread:.4f}  (раундов: {n})")
        lines += ["", "Оптимум = мин. увод центра + мин. шум + стабильность между раундами."]

        mbox.showinfo("Рекомендация по портам", "\n".join(lines))
        self.app._logln("\n".join(lines))
        with open(self.log_path.replace(".csv", "_summary.txt"), "a", encoding="utf-8") as f:
            f.write(f"\n=== Рекомендация {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
            f.write("\n".join(lines) + "\n")


# ===================================================================== main ==

def main():
    root = tk.Tk()
    JoyDiagApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
