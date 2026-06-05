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

## Ручные проверки на Windows: правильный порядок

### 1. Проверка видимости

1. `python joy_diag.py` видит нужный контроллер и показывает его VID/PID.
2. Live preview показывает оси/кнопки/POV.

### 2. Проверка USB-портов

1. На каждом USB-порте-кандидате сделать по 2–3 коротких раунда **«Снять раунд»**.
2. Нажать **«Рекомендация»**.
3. Отобрать стабильные порты по центру/разбросу.

### 3. Проверка дрожания

1. Только на стабильных портах сделать **«Замер дрожания (60с, все оси)»**.
2. Нажать **«Рекомендация по дрожанию»**.
3. Выбрать один основной порт или 1–2 лучших порта.

### 4. Замер профиля

На финальном порту:

1. `Замерить покой` создаёт разумный профиль с `device.vid` / `device.pid`.
2. `Калибровка краёв` сохраняет `calibrated_min` / `calibrated_max`, а preview использует их через `joy_core.apply_profile_axis`.
3. Сохранить `joydiag_profile_final.json`.

### 5. Проверка фидера

1. `python vjoy_feeder.py --list-devices` показывает winmm-устройства.
2. `python vjoy_feeder.py` выбирает устройство из `joydiag_profile_final.json`.
3. `python vjoy_feeder.py joydiag_profile_final.json --joy-id 0` работает с явным winmm id.
4. `python vjoy_feeder.py joydiag_profile_final.json --vid 0x07B5 --pid 0x0317` работает с явным VID/PID.
5. Фидер захватывает vJoy и пишет `vjoy_feeder.log`.
6. В `joy.cpl` vJoy-оси двигаются корректно.
7. После переподключения USB фидер заново находит контроллер и делает автоцентровку.
8. После HidHide физический контроллер скрыт от игры, но фидер продолжает его читать.
9. Автозапуск через Планировщик заданий стартует фидер после входа в Windows.

## Состояние после профильного рефакторинга

- `vjoy_feeder.py` добавлен/обновлён как profile-driven фидер.
- `joy_diag.py` не имеет fallback на конкретный VID/PID для операций с Windows-калибровкой: нужно выбрать устройство.
- `setup_hidhide.ps1` больше не имеет дефолтного VID/PID; фильтр задаётся через `-VidPid`, а устройство — через `-DevicePath`.
- Текущий `joydiag_profile_final.json` остаётся рабочим профилем, но не является ограничением кода.
- Документация фиксирует порт-first workflow: сначала стабильность портов, потом дрожание, потом покой/края.

## Решение по платформам

Проект сознательно Windows-only для GUI/боевого режима. Проверки Linux/macOS ограничены чистой математикой и профильной конфигурацией; GUI и боевой фидер там не запускаются.
