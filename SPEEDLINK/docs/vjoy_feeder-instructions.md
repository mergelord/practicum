# Инструкция: vjoy_feeder.py — боевой фидер winmm → vJoy

`vjoy_feeder.py` — постоянный фоновый модуль для личной связки Speedlink Black Widow → профиль коррекции → vJoy → MSFS.

Он читает физический джойстик через Windows `winmm`, применяет профиль `joydiag_profile_final.json` и отдаёт исправленные оси, кнопки и POV в виртуальное устройство vJoy.

## Требования

- Windows.
- Python 3.8+.
- Установленный vJoy.
- В `vJoyConf` включено устройство из `vjoy_target` профиля, обычно `#1`.
- Рядом со скриптом лежит `joydiag_profile_final.json`.
- Для скрытия физического джоя от MSFS — HidHide.

Linux/macOS не поддерживаются: это осознанно, проект сейчас личный и Windows-only.

## Запуск

```powershell
python vjoy_feeder.py
```

С явным профилем:

```powershell
python vjoy_feeder.py C:\SPEEDLINK\joydiag_profile_final.json
```

Основные флаги:

| Флаг | Назначение |
| --- | --- |
| `--no-autocenter` | Не делать автоцентровку при старте/переподключении. |
| `--autocenter-secs 1.2` | Длительность автоцентровки. |
| `--vjoy-dll C:\path\vJoyInterface.dll` | Явный путь к `vJoyInterface.dll`, если авто-поиск не сработал. |
| `--log C:\path\vjoy_feeder.log` | Путь к логу. |
| `--quiet` | Не печатать лог в консоль. |

## Что проверяет фидер

- Загружает и валидирует наличие секции `correction` в профиле.
- Ищет физический джой по VID/PID из профиля.
- Захватывает vJoy-устройство.
- При потере физического джоя ждёт переподключения и заново делает автоцентровку.
- При занятом/отключённом vJoy пишет понятную причину в лог.

## Автоцентровка

При старте и после переподключения фидер слушает стик примерно `1.2` секунды и вычисляет текущий центр для self-centering осей.

Защиты:

- если разброс во время замера больше `0.06`, автоцентр отклоняется;
- если центр дальше `0.6` от нуля, автоцентр отклоняется;
- `throttle`-оси не автоцентрируются.

Это нужно именно для симптома «после переподключения иногда уводит, иногда нет».

## Edge calibration

Если в профиле есть `calibrated_min` / `calibrated_max`, фидер сначала растягивает фактический ход оси до полного диапазона `[-1..1]`, а потом применяет center/deadzone/scale. Если диапазон подозрительно узкий, он игнорируется.

## Проверка перед MSFS

1. Запусти `python vjoy_feeder.py`.
2. Открой `joy.cpl` → vJoy Device.
3. Проверь:
   - X/Y стоят ровно в центре в покое;
   - газ Z проходит весь диапазон;
   - R/twist работает;
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

Скрыть физический джой:

```powershell
powershell -ExecutionPolicy Bypass -File setup_hidhide.ps1 -DevicePath "HID\VID_07B5&PID_0317\..."
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
| `Физический джой не найден` | VID/PID в профиле, USB-подключение, HidHide whitelist для python/pythonw. |
| Центр всё равно уводит | Увеличить `--autocenter-secs`, заново снять профиль в `joy_diag.py`, проверить Windows-калибровку. |
| MSFS видит два устройства | Включить HidHide и оставить в игре только vJoy. |
