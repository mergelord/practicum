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

Запуск:

```powershell
python -m unittest discover -s tests -v
```

На не-Windows машинах эти тесты тоже должны проходить, потому что они не используют `winmm`, vJoy и реестр. Боевые модули сознательно Windows-only.

## Последний прогон в AI-сессии 2026-06-05

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

Что этим подтверждено:

- `joy_core.py` импортируется без Windows-зависимостей;
- edge calibration через `calibrated_min` / `calibrated_max` участвует в коррекции;
- `apply_profile_axis(...)` применяет edge-remap до center/deadzone/scale;
- `to_vjoy(...)` отдаёт значения в диапазоне `1..32768`;
- runtime auto-center имеет safety-проверки;
- `joy_diag.py`, `vjoy_feeder.py` и тесты проходят синтаксическую проверку.

## Ручные проверки на Windows

1. `python joy_diag.py` видит Speedlink и показывает VID/PID `07B5/0317`.
2. Live preview показывает X/Y/Z/R и кнопки; corrected-значения считаются через `joy_core.apply_profile_axis`.
3. `Замерить покой` создаёт разумный профиль.
4. `Калибровка краёв` сохраняет `calibrated_min` / `calibrated_max`, а preview использует их через `joy_core.apply_profile_axis`.
5. `Калибровка Windows` не показывает старую кривую калибровку после сброса.
6. `python vjoy_feeder.py` захватывает vJoy и пишет `vjoy_feeder.log`.
7. В `joy.cpl` vJoy-оси двигаются корректно.
8. После переподключения USB фидер заново находит джой и делает автоцентровку.
9. После HidHide физический джой скрыт от MSFS, но фидер продолжает его читать.
10. Автозапуск через Планировщик заданий стартует фидер после входа в Windows.

## Состояние после PR #1 и PR #2

- PR #1 `Harden SPEEDLINK feeder and add tests/docs` смёржен.
- PR #2 `Refactor JoyDiag to use joy_core` смёржен.
- В `main` `joy_diag.py` уже использует `joy_core.py`.
- Документ `docs/session-2026-06-05-ai-worklog.md` хранит подробный контекст AI-сессии и историю решений.

## Решение по платформам

Проект сознательно Windows-only. Проверки Linux/macOS ограничены чистой математикой `joy_core.py`; GUI и боевой фидер там не запускаются.
