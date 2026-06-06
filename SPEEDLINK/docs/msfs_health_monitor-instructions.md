# Инструкция: msfs_health_monitor.py

`msfs_health_monitor.py` — простой Windows GUI-монитор для длительного теста **MSFS 2020** после настройки Speedlink/vJoy/HidHide.

Текущая версия целенаправленно ищет процесс:

```text
FlightSimulator.exe
```

То есть основной целевой сценарий сейчас — **Microsoft Flight Simulator 2020**.

## Что мониторит

Показывает в реальном времени и пишет CSV-лог:

```text
CPU usage
RAM used / total / %
Committed Bytes / Commit Limit / %
Pagefile size
Total disk read / write MB/s
Total disk queue length
Total disk average read / write latency, ms
NVIDIA GPU name / usage / temperature / power
Dedicated VRAM used / total / %
MSFS 2020 process status / PID
MSFS 2020 working set memory
MSFS 2020 private memory
MSFS 2020 process I/O read / write / total MB/s
```

То есть для RAM/SSD анализа есть два уровня:

```text
1. Вся система:
   RAM, commit, pagefile, общий SSD/HDD read/write, очередь диска, задержка чтения/записи.

2. Конкретно MSFS 2020:
   память процесса FlightSimulator.exe и его process I/O read/write/data MB/s.
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

`nvidia-smi` обычно ставится вместе с драйвером NVIDIA. Если он не найден, GUI всё равно будет писать RAM/commit/disk/MSFS, но GPU/VRAM будут недоступны.

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
6. Запустить MSFS 2020 и выполнить полёт.

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

### RAM процесса MSFS 2020

Смотреть поля:

```text
msfs_working_set_gb
msfs_private_memory_gb
```

`private_memory` полезна как индикатор, сколько памяти реально держит сам `FlightSimulator.exe`. Если она монотонно растёт весь полёт и не стабилизируется, это может указывать на утечку или тяжёлый сценарий/аддоны.

### SSD / диск

Смотреть поля:

```text
disk_read_mb_s
disk_write_mb_s
disk_queue_length
disk_avg_read_ms
disk_avg_write_ms
msfs_io_read_mb_s
msfs_io_write_mb_s
msfs_io_data_mb_s
```

Нормально:

```text
кратковременные пики чтения/записи
низкая очередь диска
низкая задержка чтения/записи
```

Подозрительно:

```text
долго высокая очередь диска
чтение/запись идут постоянно большими значениями
latency чтения/записи часто > 50 ms
фризы MSFS совпадают по времени с disk latency / disk queue spikes
```

Важно: общий `disk_read/write` — это вся система, а `msfs_io_*` — именно процесс MSFS 2020. Если общий диск занят, а `msfs_io_*` низкий, виновником может быть не MSFS, а другое приложение/служба.

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
2. Как росла RAM самого FlightSimulator.exe.
3. Не было ли высокой SSD/HDD latency или очереди диска во время фризов.
4. Не упиралась ли Dedicated VRAM в максимум видеокарты.
5. Не росла ли температура GPU.
6. Был ли MSFS process alive до конца полёта.
7. Были ли рядом по времени nvlddmkm / Resource-Exhaustion / disk / volmgr / WER events.
```

Если после включения pagefile commit остаётся нормальным, но VRAM постоянно у потолка и снова есть `nvlddmkm`, тогда следующая ветка диагностики — MSFS graphics settings / VRAM pressure / NVIDIA driver.

Если VRAM и commit нормальные, но в момент фризов растут `disk_queue_length`, `disk_avg_read_ms` или `disk_avg_write_ms`, тогда следующая ветка — диск/кэш/пейджинг/сценарии загрузки scenery.
