# Инструкция: feeder_gui.py — панель управления фидером

`feeder_gui.py` — небольшой GUI на `tkinter` для повседневного управления боевой связкой:

```text
Physical Speedlink -> vjoy_feeder.py -> vJoy Device -> MSFS
```

GUI не заменяет `joy_diag.py`: диагностика, замеры и создание профиля остаются в `joy_diag.py`. Панель нужна для уже настроенной боевой конфигурации.

## Что умеет

- Показывать состояние Scheduled Task `vJoyFeeder`.
- Показывать, найден ли процесс `vjoy_feeder.py`.
- Запускать / останавливать / перезапускать фидер через Scheduled Task.
- Ставить input на паузу и снимать с паузы.
- Открывать `joy.cpl`.
- Открывать `vjoy_feeder.log` и показывать хвост лога прямо в окне.
- Открывать папку `SPEEDLINK`.
- Открывать HidHide Configuration Client.
- Запрашивать HidHide list / hide / off через `setup_hidhide.ps1` с UAC.

## Запуск

Из рабочей папки:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\feeder_gui.py
```

GUI не требует дополнительных Python-пакетов.

## Пауза input

В `vjoy_feeder.py` добавлена поддержка pause-файла:

```text
vjoy_feeder.pause
```

Если файл существует рядом с профилем, фидер переходит в режим паузы.

### Что делает Safe Pause

При паузе фидер остаётся запущенным и продолжает держать `vJoy #1`, но не передаёт движения физического джоя в симулятор.

Поведение:

```text
X/Y/R/U/V self-centering axes -> центр
Z/РУД throttle                 -> последнее принятое значение
buttons                        -> отпущены
POV                            -> neutral
```

Это удобно, когда нужно перенести или поправить физический джойстик на столе, не отправляя случайные движения в MSFS.

### Resume

При снятии паузы фидер:

- заново ищет физический джой;
- делает короткую автоцентровку X/Y/R;
- сбрасывает внутреннее состояние Z hold-фильтра;
- продолжает обычную работу.

После `Resume Input` не трогать ручку примерно 1–2 секунды.

## HidHide

Рекомендуемый способ для текущей машины остаётся HidHide Configuration Client GUI, потому что ранее `HidHideCLI` не выводил список устройств.

В `feeder_gui.py` есть кнопки:

```text
Open HidHide GUI
List devices
Hide Device
Hiding OFF
```

Операции HidHide требуют прав администратора, поэтому GUI вызывает PowerShell через UAC.

### Правила HidHide

- В Applications должны быть:

```text
C:\Python314\python.exe
C:\Python314\pythonw.exe
```

- MSFS добавлять в Applications нельзя.
- Физический `8 button with vibration` / `Mega World USB Game Controllers` скрывать нужно.
- `vJoy` скрывать нельзя.

## Рекомендуемый повседневный сценарий

Перед MSFS:

1. Открыть `feeder_gui.py`.
2. Убедиться, что `Feeder process = RUNNING`.
3. Убедиться, что `Input = LIVE`.
4. Убедиться в `joy.cpl`, что физический джой скрыт, а `vJoy Device` виден.
5. Запустить MSFS.

Если нужно переставить джой:

1. Нажать `Pause Input`.
2. Переставить физический джой.
3. Поставить ручку в покой, РУД — в нужное положение.
4. Нажать `Resume Input`.
5. Не трогать ручку 1–2 секунды.

## Откат / ручное управление

Пауза вручную:

```powershell
New-Item -ItemType File -Path C:\SPEEDLINK\NEWVER\vjoy_feeder.pause -Force
```

Снять паузу вручную:

```powershell
Remove-Item C:\SPEEDLINK\NEWVER\vjoy_feeder.pause -ErrorAction SilentlyContinue
```

Остановить фидер:

```powershell
Stop-ScheduledTask -TaskName vJoyFeeder
```

Запустить фидер:

```powershell
Start-ScheduledTask -TaskName vJoyFeeder
```
