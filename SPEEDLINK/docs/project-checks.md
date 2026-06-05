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

## Ручные проверки на Windows

1. `python joy_diag.py` видит Speedlink и показывает VID/PID `07B5/0317`.
2. Live preview показывает X/Y/Z/R и кнопки; corrected-значения считаются через `joy_core.apply_profile_axis`.
3. `Замерить покой` создаёт разумный профиль.
4. `Калибровка Windows` не показывает старую кривую калибровку после сброса.
5. `python vjoy_feeder.py` захватывает vJoy и пишет `vjoy_feeder.log`.
6. В `joy.cpl` vJoy-оси двигаются корректно.
7. После переподключения USB фидер заново находит джой и делает автоцентровку.
8. После HidHide физический джой скрыт от MSFS, но фидер продолжает его читать.

## Решение по платформам

Проект сознательно Windows-only. Проверки Linux/macOS ограничены чистой математикой `joy_core.py`; GUI и боевой фидер там не запускаются.