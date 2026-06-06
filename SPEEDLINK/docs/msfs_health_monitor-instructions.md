# Инструкция: msfs_health_monitor.py

`msfs_health_monitor.py` — простой Windows GUI-монитор для длительного теста MSFS 2020 после настройки Speedlink/vJoy/HidHide.

Он показывает в реальном времени и пишет CSV-лог:

```text
CPU usage
RAM used / total / %
Committed Bytes / Commit Limit / %
Pagefile size
NVIDIA GPU name / usage / temperature / power
Dedicated VRAM used / total / %
MSFS process status / PID / memory
```

Также есть кнопка `Event snapshot`, которая выгружает свежие события Windows, важные для анализа:

```text
nvlddmkm
Resource-Exhaustion-Detector
disk
volmgr
Kernel-Power
Application Error
Windows Error Reporting
```

## Зависимости

Нужен только стандартный Python на Windows:

```text
python + tkinter
PowerShell
nvidia-smi для NVIDIA GPU metrics
```

`nvidia-smi` обычно ставится вместе с драйвером NVIDIA. Если он не найден, GUI всё равно будет писать RAM/commit/MSFS, но GPU/VRAM будут недоступны.

## Запуск

```powershell
cd C:\SPEEDLINK\NEWVER
python .\msfs_health_monitor.py
```

## Перед полётом

1. Перезагрузить Windows после включения pagefile.
2. Проверить, что pagefile остался включён:

```powershell
wmic pagefile list /format:list
```

3. Запустить обычную цепочку:

```text
Speedlink physical joystick
→ vjoy_feeder.py
→ vJoy Device
→ HidHide hides physical joystick from MSFS
→ MSFS sees only vJoy
```

4. Запустить монитор:

```powershell
python .\msfs_health_monitor.py
```

5. Нажать `Start logging`.
6. Запустить MSFS и выполнить полёт.

## Во время полёта смотреть

### Commit

Нормально:

```text
Commit used сильно ниже Commit limit
например 35 / 80 GB
```

Подозрительно:

```text
Commit used > 85% Commit limit
```

Это может снова указывать на commit pressure / low virtual memory.

### VRAM

Нормально:

```text
VRAM не упирается постоянно в потолок
```

Подозрительно:

```text
VRAM >= 90–95%
резкие фризы
падение MSFS
рядом в Event Viewer появляются nvlddmkm / DXGI errors
```

### GPU temperature

Подозрительно:

```text
GPU temp >= 83C
```

Порог условный: он не означает автоматическую аварию, но это точка внимания.

## После полёта

1. Нажать `Stop`.
2. Нажать `Event snapshot`.
3. Нажать `Open log folder`.
4. Прислать файлы из папки:

```text
C:\SPEEDLINK\NEWVER\msfs_health_logs
```

Нужны прежде всего:

```text
msfs_health_YYYYMMDD_HHMMSS.csv
event_snapshot_YYYYMMDD_HHMMSS.csv
```

## Как интерпретировать потом

Основные линии анализа:

```text
1. Не приближался ли Commit used к Commit limit.
2. Не упиралась ли Dedicated VRAM в максимум видеокарты.
3. Не росла ли температура GPU.
4. Был ли MSFS process alive до конца полёта.
5. Были ли рядом по времени nvlddmkm / Resource-Exhaustion / disk / volmgr / WER events.
```

Если после включения pagefile commit остаётся нормальным, но VRAM постоянно у потолка и снова есть `nvlddmkm`, тогда следующая ветка диагностики — MSFS graphics settings / VRAM pressure / NVIDIA driver.
