#!/usr/bin/env python3
"""Flight simulator health monitor GUI.

Windows-only Tkinter tool for live flight simulator monitoring.
It tracks CPU/RAM/commit, NVIDIA GPU/VRAM/temperature, simulator process
memory, simulator process I/O, total disk I/O, and writes CSV logs that can be
reviewed after the flight.

Supports:
- Microsoft Flight Simulator 2020: FlightSimulator.exe
- Microsoft Flight Simulator 2024: FlightSimulator2024.exe
- X-Plane 12: X-Plane.exe

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

APP_TITLE = "Flight Sim Health Monitor"
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "sim_health_logs"
DEFAULT_INTERVAL_SEC = 2.0

# Order matters: if several sims are open, prefer the newest/heaviest target.
# Keep the legacy constant name for compatibility with the existing code/logs.
MSFS_PROCESS_CANDIDATES = [
    ("FlightSimulator2024", "MSFS 2024"),
    ("FlightSimulator", "MSFS 2020"),
    ("X-Plane", "X-Plane 12"),
]

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
    "disk_read_mb_s",
    "disk_write_mb_s",
    "disk_queue_length",
    "disk_avg_read_ms",
    "disk_avg_write_ms",
    "gpu_name",
    "gpu_util_percent",
    "gpu_temp_c",
    "gpu_power_w",
    "vram_used_gb",
    "vram_total_gb",
    "vram_used_percent",
    "msfs_running",
    "msfs_version",
    "msfs_process_name",
    "msfs_pid",
    "msfs_path",
    "msfs_working_set_gb",
    "msfs_private_memory_gb",
    "msfs_io_read_mb_s",
    "msfs_io_write_mb_s",
    "msfs_io_data_mb_s",
]


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def file_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def gb(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value) / (1024 ** 3)


def mb(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value) / (1024 ** 2)


def pct(used: float | None, total: float | None) -> float | None:
    if used is None or total in (None, 0):
        return None
    return float(used) * 100.0 / float(total)


def round_or_none(value: Any, digits: int = 3) -> Any:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return value
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


def fmt(value: Any, suffix: str = "") -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


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
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        return 124, stdout, f"timeout after {timeout}s"
    except Exception as exc:
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
    """Read Windows system metrics and simulator process metrics.

    Different simulators use different executable names. We detect known
    MSFS/X-Plane process names and then resolve PerfProc I/O counters by PID instead
    of by process name. PID matching avoids the common PerfProc issue where
    duplicate process instances get names like FlightSimulator#1.
    """
    script = r'''
$ErrorActionPreference = 'Stop'
$c = Get-Counter `
    '\Memory\Committed Bytes', `
    '\Memory\Commit Limit', `
    '\Processor(_Total)\% Processor Time', `
    '\PhysicalDisk(_Total)\Disk Read Bytes/sec', `
    '\PhysicalDisk(_Total)\Disk Write Bytes/sec', `
    '\PhysicalDisk(_Total)\Current Disk Queue Length', `
    '\PhysicalDisk(_Total)\Avg. Disk sec/Read', `
    '\PhysicalDisk(_Total)\Avg. Disk sec/Write'
$os = Get-CimInstance Win32_OperatingSystem
$pf = Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue | Select-Object -First 1

$msfsCandidates = @(
    [pscustomobject]@{ Name = 'FlightSimulator2024'; Display = 'MSFS 2024' },
    [pscustomobject]@{ Name = 'FlightSimulator';     Display = 'MSFS 2020' },
    [pscustomobject]@{ Name = 'X-Plane';             Display = 'X-Plane 12' }
)
$msfs = $null
$msfsDisplay = $null
foreach ($candidate in $msfsCandidates) {
    $found = Get-Process -Name $candidate.Name -ErrorAction SilentlyContinue |
        Sort-Object StartTime -Descending -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($found) {
        $msfs = $found
        $msfsDisplay = $candidate.Display
        break
    }
}

# Fallback for future/Store naming changes. Keep it narrow enough to avoid
# unrelated processes such as dwm.exe whose window title can be "X-Plane".
if (-not $msfs) {
    $found = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match '^(FlightSimulator(2024)?|X-Plane|XPlane)$' } |
        Sort-Object StartTime -Descending -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($found) {
        $msfs = $found
        if ($found.ProcessName -like '*2024*') { $msfsDisplay = 'MSFS 2024' } elseif ($found.ProcessName -like 'X*Plane' -or $found.ProcessName -like 'XPlane') { $msfsDisplay = 'X-Plane 12' } else { $msfsDisplay = 'MSFS' }
    }
}

$perf = $null
if ($msfs) {
    $perf = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process -ErrorAction SilentlyContinue |
        Where-Object { [int]$_.IDProcess -eq [int]$msfs.Id } |
        Select-Object -First 1
}

$result = [ordered]@{}
foreach ($s in $c.CounterSamples) {
    $p = $s.Path.ToLowerInvariant()
    if ($p -like '*\memory\committed bytes') { $result.committed_bytes = [double]$s.CookedValue }
    elseif ($p -like '*\memory\commit limit') { $result.commit_limit_bytes = [double]$s.CookedValue }
    elseif ($p -like '*\processor(_total)\% processor time') { $result.cpu_percent = [double]$s.CookedValue }
    elseif ($p -like '*\physicaldisk(_total)\disk read bytes/sec') { $result.disk_read_bytes_per_sec = [double]$s.CookedValue }
    elseif ($p -like '*\physicaldisk(_total)\disk write bytes/sec') { $result.disk_write_bytes_per_sec = [double]$s.CookedValue }
    elseif ($p -like '*\physicaldisk(_total)\current disk queue length') { $result.disk_queue_length = [double]$s.CookedValue }
    elseif ($p -like '*\physicaldisk(_total)\avg. disk sec/read') { $result.disk_avg_sec_read = [double]$s.CookedValue }
    elseif ($p -like '*\physicaldisk(_total)\avg. disk sec/write') { $result.disk_avg_sec_write = [double]$s.CookedValue }
}
$result.total_visible_memory_bytes = [double]$os.TotalVisibleMemorySize * 1024
$result.free_physical_memory_bytes = [double]$os.FreePhysicalMemory * 1024
if ($pf) { $result.pagefile_allocated_mb = [double]$pf.AllocatedBaseSize } else { $result.pagefile_allocated_mb = $null }
if ($msfs) {
    $result.msfs_running = $true
    $result.msfs_version = [string]$msfsDisplay
    $result.msfs_process_name = [string]$msfs.ProcessName
    $result.msfs_pid = [int]$msfs.Id
    try { $result.msfs_path = [string]$msfs.Path } catch { $result.msfs_path = '' }
    $result.msfs_working_set_bytes = [double]$msfs.WorkingSet64
    $result.msfs_private_memory_bytes = [double]$msfs.PrivateMemorySize64
} else {
    $result.msfs_running = $false
    $result.msfs_version = $null
    $result.msfs_process_name = $null
    $result.msfs_pid = $null
    $result.msfs_path = $null
    $result.msfs_working_set_bytes = $null
    $result.msfs_private_memory_bytes = $null
}
if ($perf) {
    $result.msfs_io_read_bytes_per_sec = [double]$perf.IOReadBytesPersec
    $result.msfs_io_write_bytes_per_sec = [double]$perf.IOWriteBytesPersec
    $result.msfs_io_data_bytes_per_sec = [double]$perf.IODataBytesPersec
} else {
    $result.msfs_io_read_bytes_per_sec = $null
    $result.msfs_io_write_bytes_per_sec = $null
    $result.msfs_io_data_bytes_per_sec = $null
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
            "disk_read_mb_s": mb(win.get("disk_read_bytes_per_sec")),
            "disk_write_mb_s": mb(win.get("disk_write_bytes_per_sec")),
            "disk_queue_length": win.get("disk_queue_length"),
            "disk_avg_read_ms": (float(win["disk_avg_sec_read"]) * 1000.0) if win.get("disk_avg_sec_read") is not None else None,
            "disk_avg_write_ms": (float(win["disk_avg_sec_write"]) * 1000.0) if win.get("disk_avg_sec_write") is not None else None,
            "msfs_running": bool(win.get("msfs_running")),
            "msfs_version": win.get("msfs_version"),
            "msfs_process_name": win.get("msfs_process_name"),
            "msfs_pid": win.get("msfs_pid"),
            "msfs_path": win.get("msfs_path"),
            "msfs_working_set_gb": gb(win.get("msfs_working_set_bytes")),
            "msfs_private_memory_gb": gb(win.get("msfs_private_memory_bytes")),
            "msfs_io_read_mb_s": mb(win.get("msfs_io_read_bytes_per_sec")),
            "msfs_io_write_mb_s": mb(win.get("msfs_io_write_bytes_per_sec")),
            "msfs_io_data_mb_s": mb(win.get("msfs_io_data_bytes_per_sec")),
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
    checks = [
        ("commit_used_percent", 85, "HIGH COMMIT", "%"),
        ("vram_used_percent", 90, "HIGH VRAM", "%"),
        ("gpu_temp_c", 83, "HIGH GPU TEMP", "C"),
        ("ram_used_percent", 90, "HIGH RAM", "%"),
        ("disk_avg_read_ms", 50, "SLOW DISK READ", "ms"),
        ("disk_avg_write_ms", 50, "SLOW DISK WRITE", "ms"),
    ]
    try:
        for key, threshold, label, unit in checks:
            value = sample.get(key)
            if value not in (None, "") and float(value) >= threshold:
                warnings.append(f"{label} {float(value):.1f}{unit}")
        if not sample.get("msfs_running"):
            warnings.append("sim not running")
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
        self.geometry("1020x740")
        self.minsize(940, 640)
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
            ("Disk total", "disk", "read / write / queue"),
            ("Disk latency", "disk_latency", "read ms / write ms"),
            ("GPU", "gpu", "name"),
            ("GPU util", "gpu_util_percent", "%"),
            ("VRAM", "vram", "used / total / %"),
            ("GPU temp", "gpu_temp_c", "°C"),
            ("GPU power", "gpu_power_w", "W"),
            ("Simulator", "msfs", "version / process / pid / memory"),
            ("Sim path", "msfs_path", "exe"),
            ("Sim I/O", "msfs_io", "read / write / total"),
        ]
        for i, (label, key, unit) in enumerate(rows):
            ttk.Label(metrics, text=label + ":", width=14).grid(row=i // 2, column=(i % 2) * 3, sticky=tk.W, padx=(8, 2), pady=4)
            var = tk.StringVar(value="—")
            self.labels[key] = var
            ttk.Label(metrics, textvariable=var, width=42).grid(row=i // 2, column=(i % 2) * 3 + 1, sticky=tk.W, padx=2, pady=4)
            ttk.Label(metrics, text=unit, width=18).grid(row=i // 2, column=(i % 2) * 3 + 2, sticky=tk.W, padx=(2, 8), pady=4)

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
        log_path = LOG_DIR / f"sim_health_{file_stamp()}.csv"
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
            elif kind == "info":
                self.append_text(f"[{now_stamp()}] {payload}")
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
        self.labels["disk"].set(f"R {fmt(sample.get('disk_read_mb_s'), ' MB/s')} / W {fmt(sample.get('disk_write_mb_s'), ' MB/s')} / Q {fmt(sample.get('disk_queue_length'))}")
        self.labels["disk_latency"].set(f"R {fmt(sample.get('disk_avg_read_ms'), ' ms')} / W {fmt(sample.get('disk_avg_write_ms'), ' ms')}")
        self.labels["gpu"].set(str(sample.get("gpu_name") or "—"))
        self.labels["gpu_util_percent"].set(fmt(sample.get("gpu_util_percent"), "%"))
        self.labels["vram"].set(f"{fmt(sample.get('vram_used_gb'), ' GB')} / {fmt(sample.get('vram_total_gb'), ' GB')} / {fmt(sample.get('vram_used_percent'), '%')}")
        self.labels["gpu_temp_c"].set(fmt(sample.get("gpu_temp_c"), " °C"))
        self.labels["gpu_power_w"].set(fmt(sample.get("gpu_power_w"), " W"))
        if sample.get("msfs_running"):
            version = sample.get("msfs_version") or "MSFS"
            process_name = sample.get("msfs_process_name") or "?"
            self.labels["msfs"].set(
                f"{version} pid={sample.get('msfs_pid')} proc={process_name} "
                f"ws={fmt(sample.get('msfs_working_set_gb'), ' GB')} "
                f"private={fmt(sample.get('msfs_private_memory_gb'), ' GB')}"
            )
            self.labels["msfs_path"].set(str(sample.get("msfs_path") or "—"))
        else:
            self.labels["msfs"].set("sim not running")
            self.labels["msfs_path"].set("—")
        self.labels["msfs_io"].set(f"R {fmt(sample.get('msfs_io_read_mb_s'), ' MB/s')} / W {fmt(sample.get('msfs_io_write_mb_s'), ' MB/s')} / T {fmt(sample.get('msfs_io_data_mb_s'), ' MB/s')}")

        warnings = warning_lines(sample)
        self.warning_var.set("Warnings: " + ("; ".join(warnings) if warnings else "none"))
        version = sample.get("msfs_version") or "MSFS"
        self.append_text(
            f"[{sample.get('timestamp')}] "
            f"Commit {fmt(sample.get('commit_used_gb'), 'GB')}/{fmt(sample.get('commit_limit_gb'), 'GB')} ({fmt(sample.get('commit_used_percent'), '%')}) | "
            f"VRAM {fmt(sample.get('vram_used_gb'), 'GB')}/{fmt(sample.get('vram_total_gb'), 'GB')} ({fmt(sample.get('vram_used_percent'), '%')}) | "
            f"Sim IO R {fmt(sample.get('msfs_io_read_mb_s'), 'MB/s')} W {fmt(sample.get('msfs_io_write_mb_s'), 'MB/s')} | "
            f"Disk R {fmt(sample.get('disk_read_mb_s'), 'MB/s')} W {fmt(sample.get('disk_write_mb_s'), 'MB/s')} | "
            f"GPU {fmt(sample.get('gpu_temp_c'), 'C')} | "
            f"{version} {'ON' if sample.get('msfs_running') else 'OFF'}"
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


def export_event_snapshot(out_path: Path, hours: int = 8) -> None:
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