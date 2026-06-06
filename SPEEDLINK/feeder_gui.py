# -*- coding: utf-8 -*-
"""Small GUI control panel for vjoy_feeder.py.

The panel intentionally stays lightweight: tkinter only, no extra packages.
It controls the existing Scheduled Task, toggles the feeder pause-file, opens
joy.cpl/HidHide, and can run the HidHide PowerShell helper with UAC.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

SCRIPT_DIR = Path(__file__).resolve().parent
TASK_NAME = "vJoyFeeder"
PAUSE_FILE = SCRIPT_DIR / "vjoy_feeder.pause"
LOG_FILE = SCRIPT_DIR / "vjoy_feeder.log"
HIDHIDE_SCRIPT = SCRIPT_DIR / "setup_hidhide.ps1"
DEFAULT_VIDPID = "VID_07B5&PID_0317"


class CommandResult:
    def __init__(self, ok: bool, output: str):
        self.ok = ok
        self.output = output


def run_capture(args: list[str], timeout: float = 12.0) -> CommandResult:
    try:
        completed = subprocess.run(
            args,
            cwd=str(SCRIPT_DIR),
            text=True,
            capture_output=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return CommandResult(completed.returncode == 0, output.strip())
    except Exception as exc:
        return CommandResult(False, str(exc))


def powershell(command: str, timeout: float = 12.0) -> CommandResult:
    return run_capture(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], timeout=timeout)


def task_state() -> str:
    result = powershell(f"(Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue).State")
    if not result.ok or not result.output:
        return "UNKNOWN"
    return result.output.splitlines()[-1].strip()


def feeder_processes() -> str:
    cmd = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -match 'vjoy_feeder.py' } | "
        "Select-Object ProcessId,Name,CommandLine | Format-Table -AutoSize | Out-String"
    )
    result = powershell(cmd)
    return result.output if result.ok else ""


def open_path(path: str | Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def find_hidhide_gui() -> Path | None:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Nefarius Software Solutions" / "HidHide" / "x64" / "HidHideClient.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Nefarius Software Solutions" / "HidHide" / "HidHideClient.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Nefarius Software Solutions" / "HidHide" / "HidHideClient.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run_hidhide_script_elevated(extra_args: str) -> None:
    script = str(HIDHIDE_SCRIPT).replace("'", "''")
    arg_line = f"-NoProfile -ExecutionPolicy Bypass -File \"{script}\" {extra_args}".replace("'", "''")
    command = f"Start-Process powershell -Verb RunAs -ArgumentList '{arg_line}'"
    subprocess.Popen(["powershell", "-NoProfile", "-Command", command], cwd=str(SCRIPT_DIR))


class FeederControlPanel(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Speedlink Control Panel")
        self.geometry("780x560")
        self.minsize(720, 500)

        self.task_var = tk.StringVar(value="...")
        self.process_var = tk.StringVar(value="...")
        self.pause_var = tk.StringVar(value="...")
        self.hidhide_var = tk.StringVar(value="Use HidHide GUI to verify")
        self.device_path_var = tk.StringVar()
        self.vidpid_var = tk.StringVar(value=DEFAULT_VIDPID)

        self._build_ui()
        self.refresh_status()
        self.after(2000, self._periodic_refresh)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        status = ttk.LabelFrame(root, text="Status", padding=8)
        status.pack(fill="x")
        self._row(status, "Scheduled task:", self.task_var, 0)
        self._row(status, "Feeder process:", self.process_var, 1)
        self._row(status, "Input:", self.pause_var, 2)
        self._row(status, "HidHide:", self.hidhide_var, 3)

        feeder = ttk.LabelFrame(root, text="Feeder", padding=8)
        feeder.pack(fill="x", pady=(8, 0))
        ttk.Button(feeder, text="Start Feeder", command=self.start_feeder).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(feeder, text="Stop Feeder", command=self.stop_feeder).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(feeder, text="Restart", command=self.restart_feeder).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(feeder, text="Pause Input", command=self.pause_input).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(feeder, text="Resume Input", command=self.resume_input).grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(feeder, text="Refresh", command=self.refresh_status).grid(row=1, column=2, padx=4, pady=4, sticky="ew")
        for col in range(3):
            feeder.columnconfigure(col, weight=1)

        tools = ttk.LabelFrame(root, text="Tools", padding=8)
        tools.pack(fill="x", pady=(8, 0))
        ttk.Button(tools, text="Open joy.cpl", command=self.open_joy_cpl).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(tools, text="Open log", command=self.open_log).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(tools, text="Open folder", command=lambda: open_path(SCRIPT_DIR)).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(tools, text="Open HidHide GUI", command=self.open_hidhide_gui).grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        for col in range(4):
            tools.columnconfigure(col, weight=1)

        hide = ttk.LabelFrame(root, text="HidHide helper", padding=8)
        hide.pack(fill="x", pady=(8, 0))
        ttk.Label(hide, text="VID/PID filter:").grid(row=0, column=0, sticky="w")
        ttk.Entry(hide, textvariable=self.vidpid_var, width=28).grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Button(hide, text="List devices", command=self.list_hidhide_devices).grid(row=0, column=2, padx=4, sticky="ew")
        ttk.Button(hide, text="Hiding OFF", command=self.hidhide_off).grid(row=0, column=3, padx=4, sticky="ew")
        ttk.Label(hide, text="DevicePath:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(hide, textvariable=self.device_path_var).grid(row=1, column=1, columnspan=2, padx=4, sticky="ew", pady=(6, 0))
        ttk.Button(hide, text="Hide Device", command=self.hide_device).grid(row=1, column=3, padx=4, sticky="ew", pady=(6, 0))
        hide.columnconfigure(1, weight=1)
        hide.columnconfigure(2, weight=1)

        log_frame = ttk.LabelFrame(root, text="vjoy_feeder.log tail", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(log_frame, height=10, wrap="none")
        self.log_text.pack(fill="both", expand=True)

    def _row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Label(parent, textvariable=variable).grid(row=row, column=1, sticky="w", pady=2)
        parent.columnconfigure(1, weight=1)

    def _run_bg(self, fn, done=None) -> None:
        def worker():
            result = fn()
            if done:
                self.after(0, lambda: done(result))
            self.after(0, self.refresh_status)
        threading.Thread(target=worker, daemon=True).start()

    def start_feeder(self) -> None:
        self._run_bg(lambda: powershell(f"Start-ScheduledTask -TaskName '{TASK_NAME}'"), self._show_if_failed)

    def stop_feeder(self) -> None:
        self._run_bg(lambda: powershell(f"Stop-ScheduledTask -TaskName '{TASK_NAME}'"), self._show_if_failed)

    def restart_feeder(self) -> None:
        def command() -> CommandResult:
            first = powershell(f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue")
            time.sleep(1.0)
            second = powershell(f"Start-ScheduledTask -TaskName '{TASK_NAME}'")
            return CommandResult(first.ok and second.ok, (first.output + "\n" + second.output).strip())
        self._run_bg(command, self._show_if_failed)

    def pause_input(self) -> None:
        PAUSE_FILE.write_text("paused\n", encoding="utf-8")
        self.refresh_status()

    def resume_input(self) -> None:
        try:
            PAUSE_FILE.unlink()
        except FileNotFoundError:
            pass
        self.refresh_status()

    def open_joy_cpl(self) -> None:
        subprocess.Popen(["control", "joy.cpl"])

    def open_log(self) -> None:
        if LOG_FILE.exists():
            open_path(LOG_FILE)
        else:
            messagebox.showinfo("Log", f"Log file not found:\n{LOG_FILE}")

    def open_hidhide_gui(self) -> None:
        gui = find_hidhide_gui()
        if gui:
            open_path(gui)
        else:
            messagebox.showwarning("HidHide", "HidHide Configuration Client was not found. Open it from Start menu.")

    def list_hidhide_devices(self) -> None:
        vidpid = self.vidpid_var.get().strip()
        args = f"-VidPid \"{vidpid}\"" if vidpid else "-List"
        run_hidhide_script_elevated(args)
        self.hidhide_var.set("Device list requested with UAC")

    def hidhide_off(self) -> None:
        run_hidhide_script_elevated("-Off")
        self.hidhide_var.set("Hiding OFF requested with UAC")

    def hide_device(self) -> None:
        path = self.device_path_var.get().strip()
        if not path:
            messagebox.showwarning(
                "DevicePath required",
                "Paste exact HidHide DevicePath first, or use Open HidHide GUI for manual setup.",
            )
            return
        escaped = path.replace('"', '`"')
        run_hidhide_script_elevated(f"-DevicePath \"{escaped}\"")
        self.hidhide_var.set("Hide requested with UAC")

    def refresh_status(self) -> None:
        self.task_var.set(task_state())
        processes = feeder_processes()
        self.process_var.set("RUNNING" if "vjoy_feeder.py" in processes else "NOT FOUND")
        self.pause_var.set("PAUSED" if PAUSE_FILE.exists() else "LIVE")
        self._refresh_log()

    def _refresh_log(self) -> None:
        if LOG_FILE.exists():
            try:
                lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
                text = "\n".join(lines)
            except Exception as exc:
                text = str(exc)
        else:
            text = f"No log yet: {LOG_FILE}"
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def _periodic_refresh(self) -> None:
        self.refresh_status()
        self.after(3000, self._periodic_refresh)

    def _show_if_failed(self, result: CommandResult) -> None:
        if not result.ok:
            messagebox.showerror("Command failed", result.output or "Unknown error")


def main() -> int:
    if os.name != "nt":
        print("feeder_gui.py is intended for Windows.", file=sys.stderr)
        return 2
    app = FeederControlPanel()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
