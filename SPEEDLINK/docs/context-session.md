# SPEEDLINK — диагностика и коррекция осей через vJoy

> 🕹️ **Контекст проекта:** диагностика winmm-совместимых игровых контроллеров, построение JSON-профиля коррекции и подача исправленного сигнала в vJoy.
> _Обновлено: 2026-06-05. Текущая архитектура: profile-driven, без жёсткой привязки к конкретному VID/PID в коде._

## 0. Журнал AI-сессии 2026-06-05

Подробный журнал AI-сессии сохранён отдельно:

- [`session-2026-06-05-ai-worklog.md`](./session-2026-06-05-ai-worklog.md)

## 1. Задача

Сделать Windows-программу диагностики манипуляторов и на её основе — программную коррекцию осей контроллера, которая:

1. Определяет winmm-совместимые игровые контроллеры в системе (оси, кнопки, POV, VID/PID).
2. Проводит диагностику и выгружает её в лог (JSON + CSV).
3. По JSON-профилю применяет коррекцию осей через **vJoy + vjoy_feeder.py**.
4. Работает после переподключения контроллера и перезагрузки ПК.
5. Позволяет скрыть физический контроллер от игры через **HidHide**, чтобы игра видела только vJoy.

## 2. Поддерживаемая модель

Код не привязан к конкретному устройству. Поддерживаемая область:

- Windows;
- устройства, видимые через `joy.cpl` / `winmm` / `joyGetPosEx`;
- до 16 устройств;
- до 6 осей (`X/Y/Z/R/U/V`);
- до 32 кнопок и 1 POV;
- вывод в vJoy.

Конкретный контроллер задаётся профилем:

```json
{
  "device": {
    "name": "...",
    "vid": "0x0000",
    "pid": "0x0000",
    "joy_id": 0
  },
  "vjoy_target": 1,
  "correction": {}
}
```

`joydiag_profile_final.json` — это рабочий профиль. Его можно заменить профилем другого устройства, снятым через `joy_diag.py`.

## 3. Файлы проекта

| Файл | Назначение |
| --- | --- |
| `joy_diag.py` | **JoyDiag 2.2** — GUI на tkinter + winmm. Поиск манипуляторов, живой просмотр 6 осей, кнопок и POV, диагностика покоя, калибровка краёв, выгрузка JSON/CSV, preview через pyvjoy. Математику берёт из `joy_core.py`. |
| `joy_core.py` | Чистая математика коррекции без Windows-зависимостей: статистика, автогенерация профиля, edge-remap, deadzone, scale, invert, vJoy range, safety для auto-center. Покрыто unit-тестами. |
| `vjoy_feeder.py` | Profile-driven фидер: читает физический контроллер (winmm), применяет коррекцию по профилю через `joy_core.py`, отдаёт в vJoy через `vJoyInterface.dll`. Устойчив к переподключению. Кнопки и POV 1:1. |
| `joydiag_profile_final.json` | Текущий рабочий профиль коррекции. Содержит `device.vid/pid`, `vjoy_target` и секцию `correction`. |
| `setup_autostart.ps1` | Автозапуск фидера при входе через Планировщик задач. |
| `setup_hidhide.ps1` | Скрытие выбранного физического контроллера от игры через HidHide. |
| `tests/test_joy_core.py` | Unit-тесты критичной математики коррекции. |
| `tests/test_vjoy_feeder_config.py` | Unit-тесты profile-driven конфигурации фидера. |

## 4. Архитектура общей математики

Критичная логика вынесена в `joy_core.py`, чтобы GUI и боевой фидер не расходились:

```text
joy_core.py      = общая математика коррекции
joy_diag.py      = диагностика и preview, использует joy_core.py
vjoy_feeder.py   = боевой фидер, использует joy_core.py
```

Порядок применения профиля:

```text
raw winmm value
  -> norm_axis
  -> edge calibration remap через calibrated_min/calibrated_max
  -> center_offset/deadzone/scale/invert
  -> clamp[-1..1]
  -> vJoy 1..32768
```

Калибровка краёв не только сохраняется в профиль, но реально участвует в коррекции через `joy_core.apply_profile_axis(...)`.

## 5. Profile-driven выбор устройства

`vjoy_feeder.py` выбирает физический контроллер в таком порядке:

1. `--joy-id`, если задан;
2. `--vid` + `--pid`, если заданы;
3. `profile.device.vid` + `profile.device.pid`;
4. если VID/PID не заданы и в системе ровно один контроллер — он используется;
5. если устройств несколько и VID/PID нет — нужно запустить `--list-devices` и указать устройство явно.

Примеры:

```powershell
python vjoy_feeder.py --list-devices
python vjoy_feeder.py
python vjoy_feeder.py my_profile.json
python vjoy_feeder.py my_profile.json --vid 0x07B5 --pid 0x0317
python vjoy_feeder.py my_profile.json --joy-id 0
```

## 6. JoyDiag 2.2

`joy_diag.py` работает со всеми осями манипулятора, которые доступны через `winmm`, и использует `joy_core.py` для формул.

### Возможности

- Поиск манипуляторов и их характеристик (VID/PID, оси, кнопки, POV, диапазоны).
- Живой просмотр всех 6 осей (`X, Y, Z, R, U, V`), кнопок и POV.
- Диагностика покоя (8с): центр, шум, σ, дрейф, рекомендуемая deadzone.
- Калибровка краёв (12с): замер реальных min/max при полном отклонении каждой оси.
- Выгрузка JSON и CSV.
- Preview-коррекция в GUI через `pyvjoy`.

### Автогенерация параметров коррекции

- Если `|mean| > 0.9` и `spread < 0.02` → ось считается нецентрируемой: `type: throttle`.
- Иначе → `type: stick`:
  - `center_offset = -mean`;
  - `deadzone = spread/2 + 2σ + 0.005`;
  - `scale_pos = 1/(1+c)`, `scale_neg = 1/(1-c)`.
- Итоговое применение делается через `joy_core.apply_profile_axis(...)`.

## 7. Правильная последовательность применения

### Этап 0. Подготовка

1. Установить Python, vJoy, при необходимости HidHide.
2. В vJoyConf включить целевое устройство: оси, кнопки, POV.

### Этап 1. Диагностика

1. `python joy_diag.py` → выбрать физический контроллер.
2. «Замерить покой» → при необходимости «Калибровка краёв» → «Сохр. JSON».
3. Сохранить профиль как `joydiag_profile_final.json` или передавать его фидеру явно.

### Этап 2. Проверка коррекции

1. `python vjoy_feeder.py`.
2. `joy.cpl` → vJoy Device → проверить оси, кнопки, POV.
3. Остановить фидер (`Ctrl+C`).

### Этап 3. Скрытие от игры

1. `setup_hidhide.ps1 -List` → найти нужный HID path.
2. `setup_hidhide.ps1 -DevicePath "HID\\VID_XXXX&PID_YYYY\\..."`.
3. Запустить фидер, проверить лог.

### Этап 4. Автозапуск

```powershell
powershell -ExecutionPolicy Bypass -File setup_autostart.ps1 -RunNow
```

## 8. Известные нюансы и решения

- **SyntaxError: 'utf-8' codec can't decode byte** — файл пересохранён не в UTF-8. Решение: использовать UTF-8.
- **Ось выглядит «мёртвой» в логе** — часто ось не двигали во время замера.
- **CSV содержит только фазу покоя** — для коррекции важны центр из покоя и края из калибровки.
- **HidHide ↔ winmm:** фидер читает контроллер через winmm. Если после cloak устройство не читается — проверить whitelist python/pythonw.

## 9. Откат

- Скрытие: `setup_hidhide.ps1 -Off`.
- Автозапуск: `setup_autostart.ps1 -Remove`.
