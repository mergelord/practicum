# SPEEDLINK

Личный проект для диагностики и программной коррекции осей Speedlink Black Widow SL-6640 под Windows.

Проект не рассчитан на широкую дистрибуцию: сейчас цель — стабильная работа на моей машине с MSFS, vJoy и HidHide. Linux/macOS не являются приоритетом и не поддерживаются без отдельного запроса.

## Что внутри

| Файл | Назначение |
| --- | --- |
| `joy_diag.py` | GUI-диагностика через `winmm`: оси, кнопки, POV, VID/PID, покой, края, дрожание, USB-порты, Windows-калибровка. |
| `joy_core.py` | Чистая математика коррекции: статистика, deadzone, scale, edge-remap, vJoy range, проверка автоцентра. Покрыто тестами. |
| `vjoy_feeder.py` | Боевой фоновый модуль `winmm -> correction -> vJoy`, с автоцентровкой и переподключением. |
| `joydiag_profile_final.json` | Текущий профиль коррекции для Speedlink Black Widow. |
| `setup_autostart.ps1` | Автозапуск `vjoy_feeder.py` через Планировщик заданий Windows. |
| `setup_hidhide.ps1` | Скрытие физического джойстика от игр через HidHide, чтобы MSFS видел только vJoy. |
| `tests/test_joy_core.py` | Unit-тесты критичной математики коррекции. |
| `docs/` | Рабочие инструкции и контекст проекта. |

## Быстрый рабочий сценарий

1. Подключить Speedlink к выбранному USB-порту.
2. Запустить диагностику:

```powershell
python joy_diag.py
```

3. При необходимости сделать:
   - чтение/сброс Windows-калибровки;
   - тест центра по USB-портам;
   - тест дрожания;
   - новый замер покоя и сохранение `joydiag_profile_final.json`.
4. Проверить боевой фидер:

```powershell
python vjoy_feeder.py
```

5. Если vJoy двигается корректно — скрыть физический джой от MSFS через HidHide и включить автозапуск.

## Проверки

Математика вынесена в `joy_core.py`, чтобы её можно было проверять без Windows/vJoy:

```powershell
python -m unittest discover -s tests -v
```

На Linux/macOS тестируется только `joy_core.py`. Боевые модули `joy_diag.py` и `vjoy_feeder.py` завязаны на Windows API (`winmm.dll`, реестр, vJoyInterface.dll).

## Важные ограничения

- Целевая ОС: Windows.
- Чтение физического джоя: legacy `winmm` / `joyGetPosEx`.
- Ограничения `winmm`: до 16 устройств, до 6 осей, до 32 кнопок и 1 POV.
- Для постоянной коррекции нужен установленный vJoy.
- Для MSFS желательно HidHide, иначе игра может видеть и физический джой, и vJoy одновременно.

## Документация

- `docs/context-session.md` — полный рабочий контекст проекта.
- `docs/joy_diag-instructions.md` — как пользоваться диагностикой.
- `docs/vjoy_feeder-instructions.md` — как запускать фидер, HidHide и автозапуск.
- `docs/project-checks.md` — что проверяется автоматически и вручную.
