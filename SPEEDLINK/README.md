# SPEEDLINK

Windows-only инструменты для диагностики winmm-совместимых игровых контроллеров и программной коррекции осей через vJoy.

Проект больше не завязан в коде на конкретный VID/PID или конкретный экземпляр джойстика. Устройство выбирается из `profile.json` или через CLI-параметры. В репозитории может лежать рабочий профиль для Speedlink Black Widow SL-6640, но это профиль/пример, а не жёсткое ограничение программы.

Linux/macOS не являются целью проекта: без Windows можно проверять только чистую математику `joy_core.py`.

## Что внутри

| Файл | Назначение |
| --- | --- |
| `joy_diag.py` | GUI-диагностика через `winmm`: оси, кнопки, POV, VID/PID, покой, края, дрожание, USB-порты, Windows-калибровка. Формулы берёт из `joy_core.py`. |
| `joy_core.py` | Чистая математика коррекции: статистика, deadzone, scale, edge-remap, vJoy range, проверка автоцентра. Покрыто тестами. |
| `vjoy_feeder.py` | Боевой фоновый модуль `winmm -> correction -> vJoy`, с автоцентровкой и переподключением. Устройство выбирается из профиля или CLI. |
| `joydiag_profile_final.json` | Текущий рабочий профиль коррекции. Его можно заменить профилем любого другого winmm-совместимого устройства. |
| `setup_autostart.ps1` | Автозапуск `vjoy_feeder.py` через Планировщик заданий Windows. |
| `setup_hidhide.ps1` | Скрытие выбранного физического контроллера от игр через HidHide, чтобы игра видела только vJoy. |
| `tests/test_joy_core.py` | Unit-тесты критичной математики коррекции. |
| `tests/test_vjoy_feeder_config.py` | Unit-тесты профильного выбора устройства и POV-конвертации фидера. |
| `docs/` | Рабочие инструкции, контекст проекта и журнал AI-сессии. |

## Быстрый рабочий сценарий

1. Подключить контроллер к выбранному USB-порту.
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

5. Если vJoy двигается корректно — скрыть физический контроллер от игры через HidHide и включить автозапуск.

## Profile-driven режим

`vjoy_feeder.py` больше не содержит жёсткого `DEFAULT_VID/DEFAULT_PID`. Источник выбора физического устройства:

1. `--joy-id`, если задан;
2. `--vid` + `--pid`, если заданы;
3. `profile.device.vid` + `profile.device.pid`;
4. если VID/PID не заданы и в системе ровно один контроллер — он используется;
5. если устройств несколько и VID/PID нет — фидер просит запустить `--list-devices` и указать устройство явно.

Примеры:

```powershell
python vjoy_feeder.py --list-devices
python vjoy_feeder.py
python vjoy_feeder.py my_profile.json
python vjoy_feeder.py my_profile.json --vid 0x07B5 --pid 0x0317
python vjoy_feeder.py my_profile.json --joy-id 0
```

## Архитектура коррекции

Критичная математика вынесена в `joy_core.py`, чтобы диагностика и боевой фидер не расходились в формулах:

```text
joy_core.py      = общая математика
joy_diag.py      = GUI-диагностика, использует joy_core.py
vjoy_feeder.py   = боевой фидер, использует joy_core.py
```

Порядок применения коррекции:

```text
raw winmm value
  -> norm_axis
  -> edge calibration remap через calibrated_min/calibrated_max
  -> center_offset/deadzone/scale/invert
  -> clamp[-1..1]
  -> vJoy 1..32768
```

То есть калибровка краёв не только сохраняется в профиль, но и реально участвует в коррекции через `joy_core.apply_profile_axis(...)`.

## Проверки

Математика и профильная конфигурация проверяются без Windows/vJoy:

```powershell
python -m unittest discover -s tests -v
```

На Linux/macOS тестируются только модули без вызова Windows API. Боевые части `joy_diag.py` и `vjoy_feeder.py` запускаются только на Windows.

## Важные ограничения

- Целевая ОС боевого режима: Windows.
- Чтение физического контроллера: legacy `winmm` / `joyGetPosEx`.
- Ограничения `winmm`: до 16 устройств, до 6 осей, до 32 кнопок и 1 POV.
- Для постоянной коррекции нужен установленный vJoy.
- Для игр желательно HidHide, иначе игра может видеть и физический контроллер, и vJoy одновременно.

## Документация

- `docs/context-session.md` — полный рабочий контекст проекта.
- `docs/session-2026-06-05-ai-worklog.md` — подробный журнал AI-сессии: решения, PR, проверки, изменения и текущее состояние.
- `docs/joy_diag-instructions.md` — как пользоваться диагностикой.
- `docs/vjoy_feeder-instructions.md` — как запускать фидер, HidHide и автозапуск.
- `docs/project-checks.md` — что проверяется автоматически и вручную.
