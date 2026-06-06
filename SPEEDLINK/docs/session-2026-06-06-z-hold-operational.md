# Speedlink Black Widow — Z hold filter operational validation

Дата: 2026-06-06, день MSK.

## Цель сессии

Зафиксировать боевую проверку после мержа PR #16 `Add throttle hold filter for noisy Z axis` и текущее рабочее состояние перед тестом в MSFS.

Контекст: ранее JoyDiag-замеры показали, что ось Z/РУД дрожит даже без MSFS, то есть причина находится в физической оси/потенциометре/механике, а не в MSFS, vJoy, HidHide или драйвере. Для Z был добавлен throttle hold / anti-jitter фильтр.

## Исходное состояние перед проверкой

- PR #16 был смержен в `main`.
- Локальная рабочая папка пользователя: `C:\SPEEDLINK\NEWVER`.
- Физический джойстик: Speedlink Black Widow SL-6640 / `VID_07B5&PID_0317`.
- Текущее имя в Windows/JoyDiag: `Microsoft PC-joystick driver` / `8 button with vibration`.
- HidHide-имя физического устройства: `Mega World USB Game Controllers`.
- vJoy target: Device #1.
- vJoyConf: Device #1 включён; оси X/Y/Z/Rx/Ry/Rz; минимум 8 buttons; POV `POV 4 directions`.
- Порт: `rear3`.
- Scheduled Task: `vJoyFeeder`.
- Python для scheduled task: `C:\Python314\pythonw.exe`.

## Актуальный профиль

Ключевая часть `joydiag_profile_final.json` после PR #16:

```json
{
  "vjoy_target": 1,
  "correction": {
    "X": {"type": "stick", "deadzone": 0.010},
    "Y": {"type": "stick", "deadzone": 0.015},
    "Z": {
      "type": "throttle",
      "center_offset": 0.0,
      "deadzone": 0.0,
      "scale_pos": 1.0,
      "scale_neg": 1.0,
      "invert": false,
      "hold_threshold": 0.030
    },
    "R": {"type": "stick", "deadzone": 0.010}
  }
}
```

Смысл:

- X/Y/R — центрируемые stick/rudder-оси с deadzone.
- Z — нецентрируемый РУД/throttle, без обычной center-deadzone.
- Для Z включён hold-фильтр: если новое значение отличается от последнего отправленного меньше `hold_threshold`, в vJoy остаётся прежнее значение.
- Стартовый порог: `0.030`.
- Если в MSFS Z всё ещё гуляет — поднять до `0.035`.
- Если РУД станет слишком ступенчатым — снизить до `0.025`.

## Первичный симптом после мержа PR #16

Пользователь попробовал запустить задачу:

```powershell
PS C:\SPEEDLINK\NEWVER> Start-ScheduledTask -TaskName vJoyFeeder
PS C:\SPEEDLINK\NEWVER
```

После этого `vJoy Device` не появился/не заработал, поэтому было решено явно запустить фидер в консоли, чтобы увидеть ошибку.

Первый ручной запуск:

```powershell
PS C:\SPEEDLINK\NEWVER> python .\vjoy_feeder.py
[2026-06-06 12:17:02] profile: C:\SPEEDLINK\NEWVER\joydiag_profile_final.json
ERROR: Could not acquire vJoy #1; it may be busy or disabled
```

Диагноз: проблема была не в HidHide и не в физическом джое, потому что ошибка возникла до поиска физического устройства. Это означало, что `vJoy Device #1` был занят, отключён или находился в зависшем состоянии после предыдущего запуска.

Рекомендованная диагностика:

```powershell
cd C:\SPEEDLINK\NEWVER
Stop-ScheduledTask -TaskName vJoyFeeder -ErrorAction SilentlyContinue

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "vjoy_feeder.py" } |
  Select-Object ProcessId, Name, CommandLine
```

Если найден старый `python.exe` / `pythonw.exe` с `vjoy_feeder.py`, остановить:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "vjoy_feeder.py" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## Успешный ручной запуск

После освобождения/повторной попытки фидер успешно стартовал вручную:

```powershell
PS C:\SPEEDLINK\NEWVER> python .\vjoy_feeder.py
[2026-06-06 12:20:30] profile: C:\SPEEDLINK\NEWVER\joydiag_profile_final.json
[2026-06-06 12:20:30] vJoy #1 acquired via C:\Program Files\vJoy\x64\vJoyInterface.dll
[2026-06-06 12:20:30] physical device: id=0 Microsoft PC-joystick driver VID_07B5&PID_0317
[2026-06-06 12:20:32] auto-center X: -0.0000 spread=0.0000
[2026-06-06 12:20:32] auto-center Y: -0.0007 spread=0.0078
[2026-06-06 12:20:32] auto-center R: -0.0000 spread=0.0000
[2026-06-06 12:20:32] auto-center U: rejected mean=-1.0000 spread=0.0000
[2026-06-06 12:20:32] auto-center V: rejected mean=-1.0000 spread=0.0000
```

Интерпретация:

- `vJoy #1 acquired` — vJoy живой и захвачен.
- `physical device ... VID_07B5&PID_0317` — физический Speedlink найден.
- X и R в центре идеально.
- Y имеет малый spread `0.0078`, что ниже рабочей deadzone `0.015`.
- `U/V rejected mean=-1.0000` — штатно и не является ошибкой: эти оси у данного джойстика не используются и стоят в крайнем положении, поэтому автоцентровка правильно отказалась считать их центрируемыми стиками.

## Проверка joy.cpl после ручного запуска

Пользователь проверил `joy.cpl → vJoy Device`:

```text
vJoy Device ок все работает и стоит по центру без дрожания
```

Вывод:

- новая версия `vjoy_feeder.py` после PR #16 боеспособна;
- `vJoy Device #1` работает;
- физический Speedlink читается;
- X/Y/R стабильны;
- текущий профиль не создаёт дрожания на выходе vJoy.

## Проверка scheduled task

После успешного ручного запуска пользователь остановил ручной режим и снова запустил задачу:

```powershell
Start-ScheduledTask -TaskName vJoyFeeder
```

Результат:

```text
после Start-ScheduledTask -TaskName vJoyFeeder vJoy Device заработал. все хорошо
```

Вывод:

- scheduled task `vJoyFeeder` работает;
- проблема с первым запуском была временным занятием/зависанием vJoy #1 или старым процессом фидера, а не ошибкой нового кода.

## Включение HidHide перед MSFS

Перед запуском MSFS пользователь правильно остановился и включил HidHide, чтобы симулятор видел только vJoy, без дубля физического джойстика.

Проверенная конфигурация HidHide:

### Applications

В whitelist должны быть:

```text
C:\Python314\python.exe
C:\Python314\pythonw.exe
```

MSFS в Applications добавлять нельзя, иначе симулятор снова увидит физический джойстик.

### Devices

Скрывается физический контроллер:

```text
8 button with vibration
Mega World USB Game Controllers
VID_07B5&PID_0317
```

`vJoy` скрывать нельзя.

### Device Hiding

`Enable Device Hiding` включён.

## Итоговая проверка HidHide + vJoy

После включения HidHide пользователь подтвердил:

```text
8 button with vibration исчез vJoy Device остался и полностью рабочий
```

Это правильное боевое состояние:

```text
Physical Speedlink / 8 button with vibration
→ hidden by HidHide

vJoy Device
→ visible
→ fully working
→ MSFS should see only vJoy
```

## Текущее состояние на момент сохранения

Перед паузой и будущей проверкой в MSFS состояние такое:

```text
HidHide ON
8 button with vibration скрыт
vJoy Device виден
vJoy Device полностью рабочий
vJoyFeeder запущен через scheduled task
```

Ожидаемая проверка в MSFS:

1. MSFS должен видеть только `vJoy Device`, без физического `8 button with vibration`.
2. X/Y/R должны быть стабильны, центр без дрожания.
3. Z/РУД надо проверить в промежуточных положениях, особенно в зоне idle/reverse / тяга+реверс на одной оси.
4. Если Z всё ещё гуляет — поднять `hold_threshold` с `0.030` до `0.035`.
5. Если Z станет слишком ступенчатой — снизить `hold_threshold` до `0.025`.

## Важные выводы для будущих сессий

- Не менять Z обратно на `stick`: Z — это РУД/throttle и он физически не центрируется.
- Не добавлять обычную center-deadzone на Z: она не подходит для throttle-оси с тягой и реверсом на одной оси.
- Для Z использовать именно hold / anti-jitter фильтр.
- Не скрывать `vJoy` в HidHide.
- Не добавлять MSFS в HidHide Applications.
- Держать `C:\Python314\pythonw.exe` в HidHide whitelist, потому что scheduled task запускает feeder именно через `pythonw.exe`.
- Если `Could not acquire vJoy #1` повторится, сначала искать старый зависший `vjoy_feeder.py` / `pythonw.exe`, затем проверять vJoyConf, и только потом перезагружать Windows.

## Быстрые команды диагностики

Остановить scheduled task:

```powershell
Stop-ScheduledTask -TaskName vJoyFeeder
```

Запустить scheduled task:

```powershell
Start-ScheduledTask -TaskName vJoyFeeder
```

Ручной запуск фидера для диагностики:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\vjoy_feeder.py
```

Проверить старые процессы фидера:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "vjoy_feeder.py" } |
  Select-Object ProcessId, Name, CommandLine
```

Убить старые процессы фидера:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "vjoy_feeder.py" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Посмотреть лог:

```powershell
Get-Content C:\SPEEDLINK\NEWVER\vjoy_feeder.log -Tail 50
```
