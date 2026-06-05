# Инструкция: vjoy_feeder.py — боевой фидер winmm → vJoy

`vjoy_feeder.py` — постоянный фоновый модуль для связки:

```text
winmm-совместимый физический контроллер -> JSON-профиль коррекции -> vJoy -> игра
```

Он читает физический контроллер через Windows `winmm`, применяет профиль и отдаёт исправленные оси, кнопки и POV в виртуальное устройство vJoy.

Фидер больше не завязан в коде на конкретный VID/PID. Устройство выбирается из профиля или через CLI.

## Требования

- Windows.
- Python 3.8+.
- Установленный vJoy.
- В `vJoyConf` включено устройство из `vjoy_target` профиля, обычно `#1`.
- Рядом со скриптом лежит `joydiag_profile_final.json` или передан явный путь к профилю.
- Для скрытия физического контроллера от игры — HidHide.

Linux/macOS не поддерживаются для боевого режима, потому что используются `winmm` и `vJoyInterface.dll`.

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
| `--no-autocenter` | Не делать автоцентровку при старте/переподключении. |
| `--autocenter-secs 1.2` | Длительность автоцентровки. |
| `--vjoy-dll C:\path\vJoyInterface.dll` | Явный путь к `vJoyInterface.dll`, если авто-поиск не сработал. |
| `--log C:\path\vjoy_feeder.log` | Путь к логу. |
| `--quiet` | Не печатать лог в консоль. |

## Что проверяет фидер

- Загружает и валидирует наличие секции `correction` в профиле.
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

## Edge calibration

Если в профиле есть `calibrated_min` / `calibrated_max`, фидер сначала растягивает фактический ход оси до полного диапазона `[-1..1]`, а потом применяет center/deadzone/scale. Если диапазон подозрительно узкий, он игнорируется.

## Проверка перед игрой

1. Запусти `python vjoy_feeder.py`.
2. Открой `joy.cpl` → vJoy Device.
3. Проверь:
   - self-centering оси стоят ровно в центре в покое;
   - газ/слайдер проходит весь диапазон;
   - руль/twist работает;
   - кнопки и POV пробрасываются.
4. Только после этого включай HidHide.

## Автозапуск

```powershell
powershell -ExecutionPolicy Bypass -File setup_autostart.ps1 -RunNow
```

Откат:

```powershell
powershell -ExecutionPolicy Bypass -File setup_autostart.ps1 -Remove
```

## HidHide

Список устройств:

```powershell
powershell -ExecutionPolicy Bypass -File setup_hidhide.ps1 -List
```

Можно отфильтровать список по VID/PID:

```powershell
powershell -ExecutionPolicy Bypass -File setup_hidhide.ps1 -VidPid "VID_07B5&PID_0317"
```

Скрыть выбранный физический контроллер:

```powershell
powershell -ExecutionPolicy Bypass -File setup_hidhide.ps1 -DevicePath "HID\VID_XXXX&PID_YYYY\..."
```

Откат:

```powershell
powershell -ExecutionPolicy Bypass -File setup_hidhide.ps1 -Off
```

## Диагностика проблем

| Симптом | Что проверить |
| --- | --- |
| `vJoy #1 занят` | Закрыть второй экземпляр фидера или другую программу, держащую vJoy. |
| `vJoy #1 не включён` | Включить устройство в `vJoyConf`. |
| `Физический контроллер не найден` | VID/PID в профиле, USB-подключение, HidHide whitelist для python/pythonw. |
| Найдено несколько контроллеров | Запустить `--list-devices`, затем указать `--joy-id` или `--vid/--pid`. |
| Центр всё равно уводит | Увеличить `--autocenter-secs`, заново снять профиль в `joy_diag.py`, проверить Windows-калибровку. |
| Игра видит два устройства | Включить HidHide и оставить в игре только vJoy. |
