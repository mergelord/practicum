# Проверки проекта SPEEDLINK

## Автоматические проверки

Критичная математика вынесена в `joy_core.py`; теперь её использует и `joy_diag.py`, и `vjoy_feeder.py`. Она покрыта unit-тестами:

- статистика покоя и drift;
- автоопределение `stick` / `throttle`;
- компенсация центра;
- deadzone-remap;
- throttle passthrough и invert;
- перевод в диапазон vJoy `1..32768`;
- edge calibration через `calibrated_min` / `calibrated_max`;
- runtime auto-center override;
- safety-проверки автоцентра.

Профильная конфигурация фидера покрыта отдельными тестами:

- парсинг VID/PID в hex/decimal;
- отсутствие обязательной личной привязки VID/PID;
- чтение VID/PID из профиля;
- конвертация POV из winmm в vJoy discrete POV.

Запуск:

```powershell
python -m unittest discover -s tests -v
```

На не-Windows машинах эти тесты тоже должны проходить, потому что они не вызывают `winmm`, vJoy и реестр. Боевые модули сознательно Windows-only.

## Последний прогон в AI-сессии 2026-06-05

Базовый прогон до профильного рефакторинга:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
python -m py_compile joy_core.py joy_diag.py vjoy_feeder.py tests/test_joy_core.py
```

Результат unit-тестов:

```text
Ran 11 tests in 0.001s
OK
```

После профильного рефакторинга добавлен `tests/test_vjoy_feeder_config.py`; полный ожидаемый набор:

```powershell
python -m unittest discover -s tests -v
python -m py_compile joy_core.py joy_diag.py vjoy_feeder.py tests\test_joy_core.py tests\test_vjoy_feeder_config.py
```

Что этим подтверждается:

- `joy_core.py` импортируется без Windows-зависимостей;
- edge calibration через `calibrated_min` / `calibrated_max` участвует в коррекции;
- `apply_profile_axis(...)` применяет edge-remap до center/deadzone/scale;
- `to_vjoy(...)` отдаёт значения в диапазоне `1..32768`;
- runtime auto-center имеет safety-проверки;
- `vjoy_feeder.py` не содержит жёсткого VID/PID и выбирает устройство из CLI/profile;
- `joy_diag.py`, `vjoy_feeder.py` и тесты проходят синтаксическую проверку.

## Ручные проверки на Windows

1. `python joy_diag.py` видит нужный контроллер и показывает его VID/PID.
2. Live preview показывает X/Y/Z/R и кнопки; corrected-значения считаются через `joy_core.apply_profile_axis`.
3. `Замерить покой` создаёт разумный профиль с `device.vid` / `device.pid`.
4. `Калибровка краёв` сохраняет `calibrated_min` / `calibrated_max`, а preview использует их через `joy_core.apply_profile_axis`.
5. `Калибровка Windows` не показывает старую кривую калибровку после сброса.
6. `python vjoy_feeder.py --list-devices` показывает winmm-устройства.
7. `python vjoy_feeder.py` выбирает устройство из `joydiag_profile_final.json`.
8. `python vjoy_feeder.py joydiag_profile_final.json --joy-id 0` работает с явным winmm id.
9. `python vjoy_feeder.py joydiag_profile_final.json --vid 0x07B5 --pid 0x0317` работает с явным VID/PID.
10. Фидер захватывает vJoy и пишет `vjoy_feeder.log`.
11. В `joy.cpl` vJoy-оси двигаются корректно.
12. После переподключения USB фидер заново находит контроллер и делает автоцентровку.
13. После HidHide физический контроллер скрыт от игры, но фидер продолжает его читать.
14. Автозапуск через Планировщик заданий стартует фидер после входа в Windows.

## Состояние после профильного рефакторинга

- `vjoy_feeder.py` добавлен/обновлён как profile-driven фидер.
- `joy_diag.py` не имеет fallback на конкретный VID/PID для операций с Windows-калибровкой: нужно выбрать устройство.
- `setup_hidhide.ps1` больше не имеет дефолтного VID/PID; фильтр задаётся через `-VidPid`, а устройство — через `-DevicePath`.
- Текущий `joydiag_profile_final.json` остаётся рабочим профилем, но не является ограничением кода.

## Решение по платформам

Проект сознательно Windows-only для GUI/боевого режима. Проверки Linux/macOS ограничены чистой математикой и профильной конфигурацией; GUI и боевой фидер там не запускаются.
