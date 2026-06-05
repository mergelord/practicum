# SPEEDLINK — контекст AI-сессии 2026-06-05

Документ фиксирует полный рабочий контекст текущей сессии по проекту `SPEEDLINK`, чтобы позже можно было восстановить ход решений, изменения в коде и состояние репозитория без обращения к чату.

## Исходный запрос

Пользователь попросил прочитать содержимое репозитория:

- `https://github.com/mergelord/practicum/tree/main/SPEEDLINK`

и дать мнение о проекте.

После первичного ревью пользователь уточнил ограничения:

- проект чисто личный;
- широкая дистрибуция пока не планируется;
- Linux/macOS не являются приоритетом;
- приоритет — Windows, Speedlink Black Widow, vJoy/HidHide/MSFS;
- нужно сделать необходимые проверки, тесты, исправить боевые модули и документацию проекта.

## Цель проекта, зафиксированная в ходе сессии

`SPEEDLINK` — личный Windows-only проект для диагностики и программной коррекции осей Speedlink Black Widow SL-6640.

Целевая схема:

```text
физический Speedlink
  -> winmm / joyGetPosEx
  -> профиль коррекции
  -> vJoy
  -> MSFS
```

Физический джойстик затем скрывается от игры через HidHide, чтобы MSFS видел только исправленный vJoy-девайс.

## Основные технические решения

### 1. Общая математика вынесена в `joy_core.py`

Раньше часть формул была локально в `joy_diag.py`. В ходе сессии добавлен отдельный модуль:

- `SPEEDLINK/joy_core.py`

Его задача — чистая, тестируемая математика без Windows API, `winmm`, реестра, vJoy и GUI.

Публичные элементы `joy_core.py`:

- `AXES`
- `VMIN`
- `VMAX`
- `clamp`
- `axis_stats`
- `autogen_correction`
- `apply_correction`
- `normalize_from_range`
- `normalize_with_calibrated_range`
- `apply_profile_axis`
- `to_vjoy`
- `is_safe_autocenter`
- `build_profile`

Итоговая архитектура:

```text
joy_core.py      = общая математика коррекции
joy_diag.py      = GUI-диагностика, использует joy_core.py
vjoy_feeder.py   = боевой фидер, использует joy_core.py
```

### 2. Edge calibration теперь реально участвует в коррекции

В начале ревью был выявлен важный дефект: калибровка краёв сохранялась в профиль как `calibrated_min` / `calibrated_max`, но фактически могла не участвовать в применении коррекции.

Исправленное поведение:

```text
raw winmm value
  -> norm_axis
  -> edge calibration remap через calibrated_min/calibrated_max
  -> center_offset/deadzone/scale/invert
  -> clamp[-1..1]
  -> vJoy 1..32768
```

За это отвечает `joy_core.apply_profile_axis(...)`.

Если диапазон калибровки подозрительно маленький, он игнорируется защитой, чтобы случайно плохая калибровка не ломала ось.

### 3. `vjoy_feeder.py` добавлен как боевой модуль

Добавлен Windows-only фидер:

- читает физический джойстик через `winmm`;
- применяет профиль коррекции через `joy_core.py`;
- пишет исправленные оси в vJoy через `vJoyInterface.dll`;
- пробрасывает кнопки и POV;
- умеет переподключаться;
- делает runtime auto-center при старте и переподключении;
- пишет лог.

Поддерживаемые аргументы:

- путь к профилю;
- `--vjoy-dll`;
- `--log`;
- `--no-autocenter`;
- `--autocenter-secs`;
- `--quiet`.

### 4. `joy_diag.py` переведён на `joy_core.py`

Пользователь отдельно спросил, является ли `joy_core.py` исправленным `joy_diag.py`. Было объяснено, что нет: `joy_core.py` — общая библиотека формул, а `joy_diag.py` — GUI.

После этого пользователь попросил:

> переводи joy_diag.py на использование joy_core.py

Выполнено:

- `joy_diag.py` импортирует `AXES`, `VMIN`, `VMAX`, `axis_stats`, `autogen_correction`, `apply_profile_axis`, `to_vjoy` из `joy_core.py`;
- локальные дублирующие math-helper'ы удалены;
- live preview считает corrected-значения через `apply_profile_axis`;
- preview-коррекция через `pyvjoy` тоже использует `apply_profile_axis`;
- `joy_diag.py` теперь явно Windows-only и корректно сообщает, если запущен не на Windows.

Ключевой импорт в актуальном `main`:

```python
from joy_core import (
    AXES,
    VMAX,
    VMIN,
    apply_profile_axis,
    autogen_correction,
    axis_stats,
    to_vjoy,
)
```

## Проверки, выполненные в ходе сессии

Проверки выполнялись для чистой математики и синтаксиса модулей.

Команды:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
python -m py_compile joy_core.py joy_diag.py vjoy_feeder.py tests/test_joy_core.py
```

Результат unit-тестов:

```text
Ran 11 tests in 0.001s
OK
```

Покрытие тестами:

- статистика осей;
- drift;
- автоопределение `stick` / `throttle`;
- center offset;
- deadzone remap;
- throttle passthrough;
- invert;
- перевод в диапазон vJoy `1..32768`;
- edge calibration через `calibrated_min` / `calibrated_max`;
- runtime auto-center override;
- safety-проверки автоцентра.

Ограничение: интеграция с реальным железом (`winmm`, vJoy, HidHide, MSFS) требует финальной проверки на целевой Windows-машине.

## Pull request'ы и состояние репозитория

### PR #1 — `Harden SPEEDLINK feeder and add tests/docs`

URL:

- `https://github.com/mergelord/practicum/pull/1`

Состояние:

- создан;
- смёржен пользователем;
- закрыт.

Что вошло:

- `SPEEDLINK/README.md`;
- `SPEEDLINK/joy_core.py`;
- `SPEEDLINK/vjoy_feeder.py`;
- `SPEEDLINK/setup_autostart.ps1`;
- `SPEEDLINK/setup_hidhide.ps1`;
- `SPEEDLINK/tests/test_joy_core.py`;
- `SPEEDLINK/docs/vjoy_feeder-instructions.md`;
- `SPEEDLINK/docs/project-checks.md`;
- обновление `.gitignore`.

### PR #2 — `Refactor JoyDiag to use joy_core`

URL:

- `https://github.com/mergelord/practicum/pull/2`

Состояние:

- создан после того, как выяснилось, что PR #1 уже был смёржен до доработки `joy_diag.py`;
- смёржен пользователем;
- закрыт.

Что вошло:

- перевод `SPEEDLINK/joy_diag.py` на `joy_core.py`;
- обновление `SPEEDLINK/README.md`;
- обновление `SPEEDLINK/docs/project-checks.md`.

После мержа PR #2 проверено, что в `main` лежит обновлённый `SPEEDLINK/joy_diag.py` с SHA:

- `3fcbddcfe700a0ba30cfe634ad0bf59875d79f7c`

## Важные пояснения пользователю в ходе сессии

### Как запускать проект

Диагностика:

```powershell
cd C:\SPEEDLINK
python joy_diag.py
```

Боевой фидер:

```powershell
cd C:\SPEEDLINK
python vjoy_feeder.py
```

`joy_core.py` напрямую не запускается. Это библиотека формул для `joy_diag.py` и `vjoy_feeder.py`.

### Почему `joy_diag.py` сначала казался неизменённым

Пользователь видел `main`, где на тот момент ещё не было доработки `joy_diag.py`.

Причина:

- PR #1 уже был смёржен;
- доработка `joy_diag.py` была допушена в рабочую ветку позже;
- поэтому она не попала в уже закрытый PR #1;
- для неё был открыт и затем смёржен PR #2.

После мержа PR #2 `main` обновлён.

## Текущее состояние `main` после PR #1 и PR #2

Актуальный набор ключевых файлов:

- `.gitignore`
- `SPEEDLINK/README.md`
- `SPEEDLINK/joy_diag.py`
- `SPEEDLINK/joy_core.py`
- `SPEEDLINK/vjoy_feeder.py`
- `SPEEDLINK/joydiag_profile_final.json`
- `SPEEDLINK/setup_autostart.ps1`
- `SPEEDLINK/setup_hidhide.ps1`
- `SPEEDLINK/tests/test_joy_core.py`
- `SPEEDLINK/docs/context-session.md`
- `SPEEDLINK/docs/joy_diag-instructions.md`
- `SPEEDLINK/docs/vjoy_feeder-instructions.md`
- `SPEEDLINK/docs/project-checks.md`
- `SPEEDLINK/docs/session-2026-06-05-ai-worklog.md`

## Что ещё нужно проверить вручную на Windows

1. `python joy_diag.py` открывает GUI.
2. GUI видит Speedlink Black Widow `VID_07B5&PID_0317`.
3. Live preview показывает оси, кнопки и POV.
4. `Замерить покой` создаёт профиль через `joy_core.py`.
5. `Калибровка краёв` сохраняет `calibrated_min` / `calibrated_max`, и preview использует их через `apply_profile_axis`.
6. `python vjoy_feeder.py` открывает vJoy #1 и пишет `vjoy_feeder.log`.
7. В `joy.cpl` vJoy-оси двигаются ожидаемо.
8. После переподключения USB фидер снова находит устройство и делает runtime auto-center.
9. HidHide скрывает физический джой от MSFS, но Python остаётся в whitelist и фидер продолжает читать устройство.
10. Автозапуск через Планировщик заданий стартует фидер после входа в Windows.

## Известные ограничения

- Проект сознательно Windows-only.
- Linux/macOS не в приоритете.
- На не-Windows можно проверять только `joy_core.py` и unit-тесты.
- Реальную работу с `winmm`, vJoy, HidHide и MSFS нужно проверять на целевой машине.
- `joy_diag.py` preview через `pyvjoy` не пробрасывает POV; для игры нужен `vjoy_feeder.py`.

## Короткий итог сессии

Главный результат: проект приведён к более устойчивой архитектуре с общей тестируемой математикой.

До:

```text
joy_diag.py      = GUI + своя математика
vjoy_feeder.py   = отсутствовал/не был оформлен как боевой модуль
edge calibration = сохранялась, но могла не применяться
```

После:

```text
joy_core.py      = единая математика, покрытая тестами
joy_diag.py      = GUI, использует joy_core.py
vjoy_feeder.py   = боевой Windows-фидер, использует joy_core.py
edge calibration = участвует в коррекции
```

Документация обновлена под личный Windows-only сценарий без фокуса на широкую дистрибуцию.
