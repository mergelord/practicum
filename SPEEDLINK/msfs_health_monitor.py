#!/usr/bin/env python3
"""MSFS health monitor GUI.

Small Windows-only Tkinter tool for live MSFS/system monitoring during a flight.
It shows CPU/RAM/commit, NVIDIA GPU/VRAM/temperature, MSFS process memory,
and writes CSV logs that can be reviewed after the flight.

Designed for Evgen's SPEEDLINK/MSFS troubleshooting workflow. Uses only the
Python standard library plus Windows PowerShell and NVIDIA's nvidia-smi when
available.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

APP_TITLE = "MSFS Health Monitor"
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "msfs_health_logs"
DEFAULT_INTERVAL_SEC = 2.0

WATCH_EVENT_PROVIDERS = [
    "nvlddmkm",
    "Resource-Exhaustion-Detector",
    "disk",
    "volmgr",
    "Microsoft-Windows-Kernel-Power",
    "Application Error",
    "Windows Error Reporting",
]

CSV_FIELDS = [
    "timestamp",
    "sample_ok",
    "error",
    "cpu_percent",
    "ram_used_gb",
    "ram_total_gb",
    "ram_used_percent",
    "commit_used_gb",
    "commit_limit_gb",
    "commit_used_percent",
    "pagefile_gb",
    "gpu_name",
    "gpu_util_percent",
    "gpu_temp_c",
    "gpu_power_w",
    "vram_used_gb",
    "vram_total_gb",
    "vram_used_percent",
    "msfs_running",
    "msfs_pid",
    "msfs_working_set_gb",
    "msfs_private_memory_gb",
]


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def file_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def gb(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value) / (1024 ** 3)


def pct(used: float | None, total: float | None) -> float | None:
    if used is None or total in (None, 0):
        return None
    return float(used) * 100.0 / float(total)


def round_or_none(value: Any, digits: int = 2) -> Any:
    if value is None or value == "":
        return ""
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


def run_command(args: list[str], timeout: float = 6.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", f"timeout after {timeout}s"
    except Exception as exc:  # defensive: monitoring must not crash the GUI
        return 1, "", repr(exc)


def powershell_json(script: str, timeout: float = 8.0) -> dict[str, Any]:
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    code, out, err = run_command(args, timeout=timeout)
    if code != 0:
        raise RuntimeError(err or out or f"PowerShell exited with {code}")
    if not out:
        return {}
    return json.loads(out)


def read_windows_metrics() -> dict[str, Any]:
    # Use PowerShell because these are authoritative Windows counters and do not
    # require third-party Python packages. Output is JSON to avoid locale parsing.
    script = r'''
$ErrorActionPreference = 'Stop'
$c = Get-Counter '\Memory\Committed Bytes','\Memory\Commit Limit','\Processor(_Total)\% Processor Time'
$os = Get-CimInstance Win32_OperatingSystem
$pf = Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue | Select-Object -First 1
$msfs = Get-Process FlightSimulator -ErrorAction SilentlyContinue | Select-Object -First 1
$result = [ordered]@{}
foreach ($s in $c.CounterSamples) {
    if ($s.Path -like '*\memory\committed bytes') { $result.committed_bytes = [double]$s.CookedValue }
    elseif ($s.Path -like '*\memory\commit limit') { $result.commit_limit_bytes = [double]$s.CookedValue }
    elseif ($s.Path -like '*\processor(_total)\% processor time') { $result.cpu_percent = [double]$s.CookedValue }
}
$result.total_visible_memory_bytes = [double]$os.TotalVisibleMemorySize * 1024
$result.free_physical_memory_bytes = [double]$os.FreePhysicalMemory * 1024
if ($pf) { $result.pagefile_allocated_mb = [double]$pf.AllocatedBaseSize } else { $result.pagefile_allocated_mb = $null }
if ($msfs) {
    $result.msfs_running = $true
    $result.msfs_pid = [int]$msfs.Id
    $result.msfs_working_set_bytes = [double]$msfs.WorkingSet64
    $result.msfs_private_memory_bytes = [double]$msfs.PrivateMemorySize64
} else {
    $result.msfs_running = $false
    $result.msfs_pid = $null
    $result.msfs_working_set_bytes = $null
    $result.msfs_private_memory_bytes = $null
}
$result | ConvertTo-Json -Compress
'''
    return powershell_json(script)


def find_nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    candidates = [
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe",
        Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def read_nvidia_metrics() -> dict[str, Any]:
    smi = find_nvidia_smi()
    if not smi:
        return {"gpu_available": False, "gpu_error": "nvidia-smi not found"}
    args = [
        smi,
        "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    code, out, err = run_command(args, timeout=5.0)
    if code != 0 or not out:
        return {"gpu_available": False, "gpu_error": err or out or f"nvidia-smi exited {code}"}
    # First GPU only. CSV fields are simple but name may technically contain commas;
    # split from the right to keep the last numeric fields stable.
    line = out.splitlines()[0].strip()
    parts = [p.strip() for p in line.rsplit(",", 5)]
    if len(parts) != 6:
        return {"gpu_available": False, "gpu_error": f"unexpected nvidia-smi output: {line}"}
    name, mem_used_mb, mem_total_mb, util, temp, power = parts

    def to_float(text: str) -> float | None:
        try:
            return float(text)
        except ValueError:
            return None

    return {
        "gpu_available": True,
        "gpu_name": name,
        "vram_used_bytes": (to_float(mem_used_mb) or 0.0) * 1024 * 1024,
        "vram_total_bytes": (to_float(mem_total_mb) or 0.0) * 1024 * 1024,
        "gpu_util_percent": to_float(util),
        "gpu_temp_c": to_float(temp),
        "gpu_power_w": to_float(power),
        "gpu_error": "",
    }


def collect_sample() -> dict[str, Any]:
    sample: dict[str, Any] = {"timestamp": now_stamp(), "sample_ok": True, "error": ""}
    errors: list[str] = []

    try:
        win = read_windows_metrics()
        total_ram = win.get("total_visible_memory_bytes")
        free_ram = win.get("free_physical_memory_bytes")
        ram_used = total_ram - free_ram if total_ram is not None and free_ram is not None else None
        commit_used = win.get("committed_bytes")
        commit_limit = win.get("commit_limit_bytes")
        sample.update({
            "cpu_percent": win.get("cpu_percent"),
            "ram_used_gb": gb(ram_used),
            "ram_total_gb": gb(total_ram),
            "ram_used_percent": pct(ram_used, total_ram),
            "commit_used_gb": gb(commit_used),
            "commit_limit_gb": gb(commit_limit),
            "commit_used_percent": pct(commit_used, commit_limit),
            "pagefile_gb": (float(win["pagefile_allocated_mb"]) / 1024.0) if win.get("pagefile_allocated_mb") is not None else None,
            "msfs_running": bool(win.get("msfs_running")),
            "msfs_pid": win.get("msfs_pid"),
            "msfs_working_set_gb": gb(win.get("msfs_working_set_bytes")),
            "msfs_private_memory_gb": gb(win.get("msfs_private_memory_bytes")),
        })
    except Exception as exc:
        errors.append(f"Windows metrics: {exc}")

    gpu = read_nvidia_metrics()
    if gpu.get("gpu_available"):
        sample.update({
            "gpu_name": gpu.get("gpu_name"),
            "gpu_util_percent": gpu.get("gpu_util_percent"),
            "gpu_temp_c": gpu.get("gpu_temp_c"),
            "gpu_power_w": gpu.get("gpu_power_w"),
            "vram_used_gb": gb(gpu.get("vram_used_bytes")),
            "vram_total_gb": gb(gpu.get("vram_total_bytes")),
            "vram_used_percent": pct(gpu.get("vram_used_bytes"), gpu.get("vram_total_bytes")),
        })
    else:
        errors.append(f"GPU metrics: {gpu.get('gpu_error', 'not available')}")

    if errors:
        sample["sample_ok"] = False
        sample["error"] = " | ".join(errors)
    for field in CSV_FIELDS:
        sample.setdefault(field, "")
    return sample


def warning_lines(sample: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    commit_pct = sample.get("commit_used_percent")
    vram_pct = sample.get("vram_used_percent")
    gpu_temp = sample.get("gpu_temp_c")
    ram_pct = sample.get("ram_used_percent")
    try:
        if commit_pct not in (None, "") and float(commit_pct) >= 85:
            warnings.append(f"HIGH COMMIT {float(commit_pct):.1f}%")
        if vram_pct not in (None, "") and float(vram_pct) >= 90:
            warnings.append(f"HIGH VRAM {float(vram_pct):.1f}%")
        if gpu_temp not in (None, "") and float(gpu_temp) >= 83:
            warnings.append(f"HIGH GPU TEMP {float(gpu_temp):.0f}C")
        if ram_pct not in (None, "") and float(ram_pct) >= 90:
            warnings.append(f"HIGH RAM {float(ram_pct):.1f}%")
        if not sample.get("msfs_running"):
            warnings.append("MSFS not running")
    except Exception:
        pass
    if sample.get("error"):
        warnings.append("sample warning: " + str(sample["error"]))
    return warnings


@dataclass
class MonitorState:
    running: bool = False
    log_path: Path | None = None
    start_time: dt.datetime | None = None
    last_sample: dict[str, Any] = field(default_factory=dict)
    rows_written: int = 0


class HealthMonitorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x620")
        self.minsize(860, 560)
        self.state_data = MonitorState()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.ui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self.interval_var = tk.StringVar(value=str(DEFAULT_INTERVAL_SEC))
        self.status_var = tk.StringVar(value="IDLE")
        self.log_var = tk.StringVar(value="Log: not started")
        self.warning_var = tk.StringVar(value="Warnings: none")
        self.labels: dict[str, tk.StringVar] = {}

        self._build_ui()
        self.after(250, self._process_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(root)
        controls.pack(fill=tk.X)
        ttk.Label(controls, text="Interval, sec:").pack(side=tk.LEFT)
        ttk.Entry(controls, textvariable=self.interval_var, width=6).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Button(controls, text="Start logging", command=self.start_logging).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Stop", command=self.stop_logging).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Event snapshot", command=self.collect_events_clicked).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Open log folder", command=self.open_log_folder).pack(side=tk.LEFT, padx=4)

        ttk.Label(root, textvariable=self.status_var, font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(10, 0))
        ttk.Label(root, textvariable=self.log_var).pack(anchor=tk.W)
        ttk.Label(root, textvariable=self.warning_var, foreground="#b00020").pack(anchor=tk.W, pady=(0, 8))

        metrics = ttk.LabelFrame(root, text="Live metrics")
        metrics.pack(fill=tk.X, pady=(4, 8))

        rows = [
            ("CPU", "cpu_percent", "%"),
            ("RAM", "ram", "used / total / %"),
            ("Commit", "commit", "used / limit / %"),
            ("Pagefile", "pagefile_gb", "GB"),
            ("GPU", "gpu", "name"),
            ("GPU util", "gpu_util_percent", "%"),
            ("VRAM", "vram", "used / total / %"),
            ("GPU temp", "gpu_temp_c", "°C"),
            ("GPU power", "gpu_power_w", "W"),
            ("MSFS", "msfs", "running / pid / memory"),
        ]
        for i, (label, key, unit) in enumerate(rows):
            ttk.Label(metrics, text=label + ":", width=14).grid(row=i // 2, column=(i % 2) * 3, sticky=tk.W, padx=(8, 2), pady=4)
            var = tk.StringVar(value="—")
            self.labels[key] = var
            ttk.Label(metrics, textvariable=var, width=34).grid(row=i // 2, column=(i % 2) * 3 + 1, sticky=tk.W, padx=2, pady=4)
            ttk.Label(metrics, text=unit, width=14).grid(row=i // 2, column=(i % 2) * 3 + 2, sticky=tk.W, padx=(2, 8), pady=4)

        log_frame = ttk.LabelFrame(root, text="Recent samples / messages")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.text = tk.Text(log_frame, height=14, wrap=tk.NONE)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.configure(yscrollcommand=scroll.set)

    def append_text(self, line: str) -> None:
        self.text.insert(tk.END, line + "\n")
        self.text.see(tk.END)

    def start_logging(self) -> None:
        if self.state_data.running:
            return
        try:
            interval = max(0.5, float(self.interval_var.get().replace(",", ".")))
        except ValueError:
            messagebox.showerror(APP_TITLE, "Interval must be a number, e.g. 2")
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"msfs_health_{file_stamp()}.csv"
        self.state_data = MonitorState(running=True, log_path=log_path, start_time=dt.datetime.now())
        self.stop_event.clear()
        self.worker = threading.Thread(target=self._worker_loop, args=(interval, log_path), daemon=True)
        self.worker.start()
        self.status_var.set("RUNNING")
        self.log_var.set(f"Log: {log_path}")
        self.append_text(f"[{now_stamp()}] logging started: {log_path}")

    def stop_logging(self) -> None:
        if not self.state_data.running:
            return
        self.stop_event.set()
        self.state_data.running = False
        self.status_var.set("STOPPING...")
        self.append_text(f"[{now_stamp()}] stop requested")

    def _worker_loop(self, interval: float, log_path: Path) -> None:
        try:
            with log_path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()
                while not self.stop_event.is_set():
                    started = time.monotonic()
                    sample = collect_sample()
                    row = {field: round_or_none(sample.get(field), 3) for field in CSV_FIELDS}
                    writer.writerow(row)
                    f.flush()
                    self.state_data.rows_written += 1
                    self.ui_queue.put(("sample", sample))
                    elapsed = time.monotonic() - started
                    self.stop_event.wait(max(0.0, interval - elapsed))
        except Exception as exc:
            self.ui_queue.put(("error", repr(exc)))
        finally:
            self.ui_queue.put(("stopped", str(log_path)))

    def _process_queue(self) -> None:
        while True:
            try:
                kind, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "sample":
                self.update_metrics(payload)
            elif kind == "error":
                self.append_text(f"[{now_stamp()}] ERROR: {payload}")
                self.status_var.set("ERROR")
            elif kind == "stopped":
                self.status_var.set("IDLE")
                self.append_text(f"[{now_stamp()}] logging stopped: {payload}")
        self.after(250, self._process_queue)

    def update_metrics(self, sample: dict[str, Any]) -> None:
        self.state_data.last_sample = sample
        self.labels["cpu_percent"].set(fmt(sample.get("cpu_percent"), "%"))
        self.labels["ram"].set(f"{fmt(sample.get('ram_used_gb'), ' GB')} / {fmt(sample.get('ram_total_gb'), ' GB')} / {fmt(sample.get('ram_used_percent'), '%')}")
        self.labels["commit"].set(f"{fmt(sample.get('commit_used_gb'), ' GB')} / {fmt(sample.get('commit_limit_gb'), ' GB')} / {fmt(sample.get('commit_used_percent'), '%')}")
        self.labels["pagefile_gb"].set(fmt(sample.get("pagefile_gb"), " GB"))
        self.labels["gpu"].set(str(sample.get("gpu_name") or "—"))
        self.labels["gpu_util_percent"].set(fmt(sample.get("gpu_util_percent"), "%"))
        self.labels["vram"].set(f"{fmt(sample.get('vram_used_gb'), ' GB')} / {fmt(sample.get('vram_total_gb'), ' GB')} / {fmt(sample.get('vram_used_percent'), '%')}")
        self.labels["gpu_temp_c"].set(fmt(sample.get("gpu_temp_c"), " °C"))
        self.labels["gpu_power_w"].set(fmt(sample.get("gpu_power_w"), " W"))
        if sample.get("msfs_running"):
            self.labels["msfs"].set(f"RUNNING pid={sample.get('msfs_pid')} ws={fmt(sample.get('msfs_working_set_gb'), ' GB')} private={fmt(sample.get('msfs_private_memory_gb'), ' GB')}")
        else:
            self.labels["msfs"].set("not running")

        warnings = warning_lines(sample)
        self.warning_var.set("Warnings: " + ("; ".join(warnings) if warnings else "none"))
        self.append_text(
            f"[{sample.get('timestamp')}] "
            f"CPU {fmt(sample.get('cpu_percent'), '%')} | "
            f"Commit {fmt(sample.get('commit_used_gb'), 'GB')}/{fmt(sample.get('commit_limit_gb'), 'GB')} ({fmt(sample.get('commit_used_percent'), '%')}) | "
            f"VRAM {fmt(sample.get('vram_used_gb'), 'GB')}/{fmt(sample.get('vram_total_gb'), 'GB')} ({fmt(sample.get('vram_used_percent'), '%')}) | "
            f"GPU {fmt(sample.get('gpu_temp_c'), 'C')} | "
            f"MSFS {'ON' if sample.get('msfs_running') else 'OFF'}"
        )

    def collect_events_clicked(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        out_path = LOG_DIR / f"event_snapshot_{file_stamp()}.csv"
        self.append_text(f"[{now_stamp()}] collecting event snapshot...")
        threading.Thread(target=self._collect_events_worker, args=(out_path,), daemon=True).start()

    def _collect_events_worker(self, out_path: Path) -> None:
        try:
            export_event_snapshot(out_path)
            self.ui_queue.put(("info", f"event snapshot saved: {out_path}"))
        except Exception as exc:
            self.ui_queue.put(("error", f"event snapshot failed: {exc}"))

    def open_log_folder(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(LOG_DIR)  # type: ignore[attr-defined]


def fmt(value: Any, suffix: str = "") -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def export_event_snapshot(out_path: Path, hours: int = 8) -> None:
    # Pull recent relevant System/Application events into CSV for later analysis.
    provider_array = "@(" + ",".join([repr(p) for p in WATCH_EVENT_PROVIDERS]) + ")"
    ps_path = json.dumps(str(out_path))
    script = r'''
$ErrorActionPreference = 'SilentlyContinue'
$since = (Get-Date).AddHours(-__HOURS__)
$providers = __PROVIDERS__
$events = @()
foreach ($log in @('System','Application')) {
    $events += Get-WinEvent -LogName $log -ErrorAction SilentlyContinue |
        Where-Object { $_.TimeCreated -ge $since -and ($providers -contains $_.ProviderName -or $providers -contains $_.ProviderName.Split('/')[0]) } |
        Select-Object TimeCreated, LogName, ProviderName, Id, LevelDisplayName, Message
}
$events | Sort-Object TimeCreated | Export-Csv -NoTypeInformation -Encoding UTF8 -Path __OUT_PATH__
'''.replace("__HOURS__", str(int(hours))).replace("__PROVIDERS__", provider_array).replace("__OUT_PATH__", ps_path)
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    code, out, err = run_command(args, timeout=30.0)
    if code != 0:
        raise RuntimeError(err or out or f"PowerShell exited {code}")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This monitor is Windows-only.")
    app = HealthMonitorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
