# Инструкция: vjoy_feeder.py — боевой фидер winmm → vJoy

`vjoy_feeder.py` — постоянный фоновый модуль для связки:

```text
winmm-совместимый физический контроллер -> JSON-профиль коррекции -> vJoy -> игра
```

Он читает физический контроллер через Windows `winmm`, применяет профиль и отдаёт исправленные оси, кнопки и POV в виртуальное устройство vJoy.

Фидер больше не завязан в коде на конкретный VID/PID. Устройство выбирается из профиля или через CLI.

Для повседневного запуска/паузы/HidHide добавлена отдельная панель управления: `feeder_gui.py`. См. `docs/feeder_gui-instructions.md`.

## Требования

- Windows.
- Python 3.8+.
- Установленный vJoy.
- В `vJoyConf` включено устройство из `vjoy_target` профиля, обычно `#1`.
- Рядом со скриптом лежит `joydiag_profile_final.json` или передан явный путь к профилю.
- Для скрытия физического контроллера от игры — HidHide.

Linux/macOS не поддерживаются для боевого режима, потому что используются `winmm` и `vJoyInterface.dll`.

## Рабочая конфигурация Speedlink Black Widow после восстановления

Актуальная рабочая связка для текущего Speedlink Black Widow SL-6640:

```text
Физический джой: VID_07B5&PID_0317
Windows/joy.cpl до скрытия: 8 button with vibration
JoyDiag/winmm: Microsoft PC-joystick driver
HidHide: Mega World USB Game Controllers
USB-порт: rear3
Драйвер: стандартный Microsoft HID/DirectInput
vJoy target: Device #1
POV в vJoyConf: POV 4 directions
```

Старый `SL-6640-SBK_Driver_V4.0` пока не рекомендуется: на текущей машине он раньше давал дрожание/увод X, а стандартный Microsoft-драйвер даёт более стабильный базовый сигнал.

Рекомендуемые deadzone в профиле для текущей механики и вибраций стола:

```text
X: 0.010
Y: 0.015
R/twist: 0.010
Z/РУД: 0.000
```

Z/РУД должен быть `type: "throttle"`, без автоцентровки и без deadzone.

## Настройка vJoyConf

Для `vJoy Device #1` включить:

```text
Axes: X, Y, Z, Rx, Ry, Rz
Buttons: 8 или больше
POV: POV 4 directions
```

Если vJoyConf предлагает выбор между `1 continuous` и `POV 4 directions`, выбрать **POV 4 directions**. Текущий фидер использует дискретную хатку через `SetDiscPov(...)`.

## Запуск

С профилем по умолчанию рядом со скриптом:

```powershell
python vjoy_feeder.py
```

С явным профилем:

```powershell
python vjoy_feeder.py C:\SPEEDLINK\my_profile.json
```

Посмотреть устройства, видимые через `winmm`:

```powershell
python vjoy_feeder.py --list-devices
```

Выбрать устройство явно:

```powershell
python vjoy_feeder.py my_profile.json --vid 0x07B5 --pid 0x0317
python vjoy_feeder.py my_profile.json --joy-id 0
```

## Пауза input

Фидер поддерживает pause-файл. По умолчанию это:

```text
vjoy_feeder.pause
```

рядом с профилем `joydiag_profile_final.json`.

Если файл существует, фидер переходит в safe pause:

```text
X/Y/R/U/V self-centering axes -> центр
Z/РУД throttle                 -> последнее принятое значение
buttons                        -> отпущены
POV                            -> neutral
```

Снять паузу — удалить файл. После снятия паузы фидер заново ищет физический джой, делает автоцентровку X/Y/R и сбрасывает hold-state Z.

Задать другой pause-файл:

```powershell
python vjoy_feeder.py --pause-file C:\SPEEDLINK\NEWVER\my.pause
```

Вручную поставить на паузу:

```powershell
New-Item -ItemType File -Path C:\SPEEDLINK\NEWVER\vjoy_feeder.pause -Force
```

Вручную снять паузу:

```powershell
Remove-Item C:\SPEEDLINK\NEWVER\vjoy_feeder.pause -ErrorAction SilentlyContinue
```

Удобнее делать это через `feeder_gui.py`.

## Output map: переназначение физических осей в vJoy

По умолчанию фидер работает как раньше:

```text
physical X -> vJoy X
physical Y -> vJoy Y
physical Z -> vJoy Z
physical R/twist -> vJoy Rx
physical U -> vJoy Ry
physical V -> vJoy Rz
```

Это можно изменить в профиле через секцию `output_map`.

Пример обычной identity-схемы:

```json
"output_map": {
  "X": ["X"],
  "Y": ["Y"],
  "Z": ["Z"],
  "R": ["Rx"],
  "U": ["Ry"],
  "V": ["Rz"]
}
```

Пример no-pedals / Fenix-схемы, где физическая X одновременно идёт в vJoy X и vJoy Rx, а физический twist/R игнорируется:

```json
"output_map": {
  "X": ["X", "Rx"],
  "Y": ["Y"],
  "Z": ["Z"],
  "R": [],
  "U": [],
  "V": []
}
```

В этой схеме:

```text
physical X -> vJoy X + vJoy Rx
physical R/twist -> не отправляется
vJoy Ry/Rz -> центр
```

Это удобно, если в MSFS/Fenix нужно повесить одну физическую X-ось сразу на:

```text
Aileron Axis             = vJoy X
Rudder Axis              = vJoy X
Nose Wheel Steering Axis = vJoy Rx или vJoy X
```

Если Fenix A319 упрямо цепляет `Rx` для nose wheel steering/tiller, он всё равно получит физическую X, потому что `vJoy Rx` теперь копия `vJoy X`.

Важно: при такой схеме любое движение X в полёте одновременно даёт aileron и rudder. Это компромисс для сценария без педалей.

## Как выбирается физическое устройство

Приоритет выбора:

1. `--joy-id`, если задан.
2. `--vid` + `--pid`, если заданы вместе.
3. `device.vid` + `device.pid` из JSON-профиля.
4. Если VID/PID не заданы и в системе ровно один контроллер — используется он.
5. Если устройств несколько и VID/PID нет — фидер завершится с подсказкой использовать `--list-devices`, `--joy-id` или `--vid/--pid`.

Это убирает личную привязку из кода, но сохраняет удобство: для текущего рабочего профиля запуск остаётся `python vjoy_feeder.py`.

## Основные флаги

| Флаг | Назначение |
| --- | --- |
| `--list-devices` | Показать winmm-устройства и выйти. |
| `--vid 0xXXXX --pid 0xYYYY` | Переопределить VID/PID из профиля. |
| `--joy-id N` | Использовать конкретный winmm id вместо VID/PID. |
| `--vjoy-target N` | Переопределить `vjoy_target` из профиля. |
| `--pause-file PATH` | Путь к pause-файлу. |
| `--no-autocenter` | Не делать автоцентровку при старте/переподключении. |
| `--autocenter-secs 1.2` | Длительность автоцентровки. |
| `--vjoy-dll C:\path\vJoyInterface.dll` | Явный путь к `vJoyInterface.dll`, если авто-поиск не сработал. |
| `--log C:\path\vjoy_feeder.log` | Путь к логу. |
| `--quiet` | Не печатать лог в консоль. |

## Что проверяет фидер

- Загружает и валидирует наличие секции `correction` в профиле.
- Валидирует `output_map`, если он задан.
- Выбирает физический контроллер по CLI/profile/single-device fallback.
- Захватывает vJoy-устройство.
- При потере физического контроллера ждёт переподключения и заново делает автоцентровку.
- При занятом/отключённом vJoy пишет понятную причину в лог.

## Автоцентровка

При старте и после переподключения фидер слушает self-centering оси примерно `1.2` секунды и вычисляет текущий центр.

Защиты:

- если разброс во время замера больше `0.06`, автоцентр отклоняется;
- если центр дальше `0.6` от нуля, автоцентр отклоняется;
- `throttle`-оси не автоцентрируются.

`auto-center Y: rejected ...` в логе не обязательно ошибка. Это значит, что фидер увидел нестабильную Y в момент старта и отказался брать её как новый runtime-центр. Если `joy.cpl -> vJoy Device` после этого стоит ровно, запуск считается рабочим.

## Edge calibration

Если в профиле есть `calibrated_min` / `calibrated_max`, фидер сначала растягивает фактический ход оси до полного диапазона `[-1..1]`, а потом применяет center/deadzone/scale. Если диапазон подозрительно узкий, он игнорируется.

## Проверка перед игрой

1. Запусти `python vjoy_feeder.py` или scheduled task `vJoyFeeder`.
2. Открой `joy.cpl` → vJoy Device.
3. Проверь:
   - X/Y стоят ровно в центре в покое;
   - если включён no-pedals `output_map`, то vJoy Rx двигается вместе с X, а не с физическим twist/R;
   - Z/РУД проходит весь диапазон и остаётся там, где оставлен;
   - кнопки и POV пробрасываются.
4. Только после этого включай HidHide.

## Автозапуск

Запускать из PowerShell от администратора:

```powershell
cd C:\SPEEDLINK\NEWVER
powershell -ExecutionPolicy Bypass -File .\setup_autostart.ps1 -RunNow
```

Если получить:

```text
Register-ScheduledTask : Access is denied
HRESULT 0x80070005
```

значит PowerShell не elevated. Открой PowerShell через **Run as administrator** и повтори команду.

Проверка:

```powershell
Get-Content .\vjoy_feeder.log -Tail 30
```

Ожидаемые признаки:

```text
vJoy #1 acquired
physical device: id=0 Microsoft PC-joystick driver VID_07B5&PID_0317
auto-center X ...
auto-center R ...
```

Откат:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_autostart.ps1 -Remove
```

## HidHide

### Через CLI-скрипт

Список устройств:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_hidhide.ps1 -List
```

Можно отфильтровать список по VID/PID:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_hidhide.ps1 -VidPid "VID_07B5&PID_0317"
```

Скрыть выбранный физический контроллер:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_hidhide.ps1 -DevicePath "HID\VID_XXXX&PID_YYYY\..."
```

Откат:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_hidhide.ps1 -Off
```

### Если HidHideCLI не выводит список устройств

На текущей машине HidHideCLI может не отдавать список устройств. В этом случае настрой HidHide через **HidHide Configuration Client** GUI:

1. Вкладка **Applications**:
   - добавить `C:\Python314\python.exe`;
   - добавить `C:\Python314\pythonw.exe`.
2. **Не добавлять MSFS** в Applications.
3. Вкладка **Devices**:
   - скрыть `Mega World USB Game Controllers`;
   - **не скрывать vJoy**.
4. Включить **Enable Device Hiding**.

После включения HidHide физический `8 button with vibration` / `Mega World USB Game Controllers` должен исчезнуть из `joy.cpl`, а `vJoy Device` должен остаться видимым и рабочим.

## Диагностика проблем

| Симптом | Что проверить |
| --- | --- |
| `vJoy #1 занят` | Закрыть второй экземпляр фидера или другую программу, держащую vJoy. |
| `vJoy #1 не включён` | Включить устройство в `vJoyConf`. |
| `Физический контроллер не найден` | VID/PID в профиле, USB-подключение, HidHide whitelist для python/pythonw. |
| Найдено несколько контроллеров | Запустить `--list-devices`, затем указать `--joy-id` или `--vid/--pid`. |
| `auto-center Y: rejected` | Если vJoy Y стоит ровно, это штатная защита, не ошибка. |
| Центр всё равно уводит | Проверить Windows-калибровку, deadzone, механику стика и вибрации стола. |
| Игра видит два устройства | Включить HidHide и оставить в игре только vJoy. |
| После HidHide фидер потерял физический джой | Добавить в Applications именно тот Python, которым запущен фидер, особенно `pythonw.exe` для scheduled task. |
| Fenix цепляет nose wheel steering на Rx | Включить `output_map`: `X -> [X, Rx]`, `R -> []`, затем назначить Nose Wheel Steering на vJoy Rx. |
