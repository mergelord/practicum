# Speedlink Black Widow — feeder GUI / pause control session

Дата: 2026-06-06, вечер MSK.

## Цель сессии

Зафиксировать контекст после успешного боевого теста связки Speedlink Black Widow → vJoy → MSFS и начала разработки GUI-панели управления фидером.

Ключевая пользовательская задача: вместо ручных PowerShell-команд получить простой GUI, в котором можно:

- запускать и останавливать фидер;
- ставить input фидера на паузу без полного выключения фидера;
- снимать input с паузы;
- видеть состояние фидера и лог;
- управлять или открывать HidHide для скрытия физического джоя.

## Боевое состояние перед началом GUI

Перед началом этой части связка уже была проверена в MSFS.

Пользователь сообщил:

```text
в 1,5 полете все было хорошо
```

Это означает, что предыдущий фикс Z/РУД через `hold_threshold = 0.030` успешно прошёл предварительный длительный тест:

- MSFS видел `vJoy Device`;
- физический `8 button with vibration` был скрыт через HidHide;
- X/Y/R не дрожали;
- Z/РУД в полёте не создавал видимых проблем;
- дубля физического джойстика в MSFS не было.

Текущая рабочая цепочка:

```text
Physical Speedlink Black Widow / VID_07B5&PID_0317
→ hidden by HidHide
→ visible to C:\Python314\pythonw.exe through HidHide whitelist
→ vjoy_feeder.py reads it through winmm
→ vJoy Device #1 receives corrected axes/buttons/POV
→ MSFS sees only vJoy Device
```

## Обсуждение выключения фидера

Для полного временного выключения фидера был подтверждён ручной способ:

```powershell
Stop-ScheduledTask -TaskName vJoyFeeder
```

Для включения:

```powershell
Start-ScheduledTask -TaskName vJoyFeeder
```

Но пользователь справедливо заметил, что для сценария «перенести джой со стола» лучше не останавливать весь scheduled task, а ставить на паузу именно input внутри фидера.

Вывод:

```text
Stop/Start task — грубый способ.
Feeder input pause — правильный способ для повседневного использования.
```

## Требуемое поведение паузы

Пауза должна работать без остановки процесса фидера:

- фидер остаётся запущен;
- `vJoy #1` остаётся захвачен;
- HidHide не трогаем;
- MSFS продолжает видеть `vJoy Device`;
- физический джой можно двигать/переносить, но новые движения не уходят в vJoy/MSFS.

Выбран режим **Safe Pause**:

```text
X/Y/R/U/V self-centering axes -> центр
Z/РУД throttle                 -> последнее принятое значение
buttons                        -> отпущены
POV                            -> neutral
```

Причина:

- для переноса джоя со стола безопаснее центрировать stick-оси;
- Z/РУД нельзя центрировать, потому что это throttle, поэтому держим последнее принятое значение;
- кнопки и POV безопаснее отпускать.

После `Resume Input` фидер должен:

- заново найти физический джой;
- сделать короткую автоцентровку X/Y/R;
- сбросить внутренний `hold_state` Z;
- продолжить нормальную работу.

Практическое правило после resume:

```text
Поставить ручку в покой, РУД в нужное положение, нажать Resume Input и 1–2 секунды не трогать стик.
```

## Решение: pause-файл

Для простоты и надёжности выбран механизм pause-файла:

```text
C:\SPEEDLINK\NEWVER\vjoy_feeder.pause
```

Если файл существует — фидер в паузе.

Если файла нет — фидер работает в обычном режиме.

Ручные команды:

```powershell
New-Item -ItemType File -Path C:\SPEEDLINK\NEWVER\vjoy_feeder.pause -Force
```

```powershell
Remove-Item C:\SPEEDLINK\NEWVER\vjoy_feeder.pause -ErrorAction SilentlyContinue
```

GUI просто создаёт и удаляет этот файл.

## Изменения в vjoy_feeder.py

В PR #18 добавлена поддержка настоящей паузы input:

- константа `DEFAULT_PAUSE_FILE = "vjoy_feeder.pause"`;
- CLI-флаг `--pause-file PATH`;
- функция `pause_axis_value(...)`;
- функция `feed_pause_once(...)`;
- `feed_once(...)` теперь возвращает последние отправленные значения осей;
- основной цикл проверяет наличие pause-файла;
- при входе в паузу логирует:

```text
input paused
```

- при выходе из паузы логирует:

```text
input resumed; re-acquiring device and auto-centering
```

- при выходе из паузы сбрасывает:

```text
runtime_centers
hold_state
last_outputs
current_id/current_caps
```

Это заставляет фидер после паузы заново пройти безопасный путь подключения и автоцентровки.

## Новый GUI

Добавлен файл:

```text
SPEEDLINK/feeder_gui.py
```

GUI сделан на `tkinter`, без дополнительных зависимостей.

Назначение: повседневная панель управления уже настроенной боевой связкой, а не замена `joy_diag.py`.

`joy_diag.py` остаётся для диагностики, замеров и создания профиля.

`feeder_gui.py` — для запуска, остановки, паузы, логов и HidHide.

## Возможности feeder_gui.py

Панель показывает:

- состояние Scheduled Task `vJoyFeeder`;
- найден ли процесс `vjoy_feeder.py`;
- состояние input: `LIVE` / `PAUSED`;
- хвост `vjoy_feeder.log`.

Кнопки Feeder:

```text
Start Feeder
Stop Feeder
Restart
Pause Input
Resume Input
Refresh
```

Кнопки Tools:

```text
Open joy.cpl
Open log
Open folder
Open HidHide GUI
```

HidHide helper:

```text
List devices
Hide Device
Hiding OFF
```

## HidHide через GUI

HidHide-операции требуют админ-прав, поэтому GUI вызывает PowerShell helper через UAC.

Важно: на текущей машине ранее `HidHideCLI` не выводил список устройств, поэтому основной безопасный путь остаётся:

```text
Open HidHide GUI → настроить через HidHide Configuration Client
```

Правила HidHide остаются прежними:

- скрывать физический `8 button with vibration` / `Mega World USB Game Controllers`;
- не скрывать `vJoy`;
- держать в Applications:

```text
C:\Python314\python.exe
C:\Python314\pythonw.exe
```

- не добавлять MSFS в HidHide Applications.

## Документация

Добавлен новый документ:

```text
SPEEDLINK/docs/feeder_gui-instructions.md
```

Обновлена инструкция:

```text
SPEEDLINK/docs/vjoy_feeder-instructions.md
```

В документации зафиксированы:

- назначение `feeder_gui.py`;
- запуск GUI;
- Safe Pause;
- ручное управление pause-файлом;
- HidHide-ограничения;
- рекомендуемый повседневный сценарий.

## Тесты

Обновлён файл:

```text
SPEEDLINK/tests/test_vjoy_feeder_config.py
```

Добавлен тест:

```text
test_pause_axis_value_centers_sticks_and_holds_throttle
```

Проверяется:

- stick-оси в паузе центрируются;
- throttle-ось держит последнее значение;
- throttle без последнего значения получает безопасный fallback `0.0`.

## PR

Открыт PR:

```text
https://github.com/mergelord/practicum/pull/18
```

Название:

```text
Add Speedlink feeder control GUI
```

Branch:

```text
speedlink-feeder-control-gui
```

Основной commit после добавления GUI:

```text
9719e39282e5af8d5699458972d874d254981bde
```

## Как проверять после мержа/копирования

После мержа или копирования файлов в рабочую папку:

```powershell
cd C:\SPEEDLINK\NEWVER
python .\feeder_gui.py
```

Проверка:

1. GUI открывается без ошибок.
2. `Start Feeder` запускает scheduled task.
3. `Stop Feeder` останавливает scheduled task.
4. `Pause Input` создаёт `vjoy_feeder.pause`.
5. В логе появляется `input paused`.
6. В `joy.cpl → vJoy Device` X/Y/R должны уйти/стоять в центре, Z остаётся на последнем принятом значении, кнопки отпущены, POV neutral.
7. `Resume Input` удаляет pause-файл.
8. В логе появляется `input resumed; re-acquiring device and auto-centering`.
9. После 1–2 секунд покоя фидер продолжает нормальную работу.
10. `Open joy.cpl`, `Open log`, `Open folder` работают.
11. `Open HidHide GUI` открывает HidHide Configuration Client, если найден.

## Важные предупреждения для будущих правок

- Не превращать `feeder_gui.py` в диагностический комбайн: диагностика остаётся в `joy_diag.py`.
- Не добавлять MSFS в HidHide Applications.
- Не скрывать `vJoy`.
- Не центрировать Z/РУД при паузе: Z — throttle, её надо держать в последнем принятом положении.
- Не удалять поддержку ручного pause-файла: это простой аварийный и прозрачный механизм.
- Если потребуется более удобный UX, можно позже добавить tray icon или сборку `.exe`, но текущий первый вариант должен оставаться простым и проверяемым.
