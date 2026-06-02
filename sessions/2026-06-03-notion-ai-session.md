# Контекст сессии Notion AI — 2026-06-03

> Полный конспект сессии. Темы: математика (Эрдёш) → ИИ/кибербезопасность и геополитика → квантовые вычисления → анализ Lua-малвари → разработка кастомного резольвера для neverlose CS:GO (HVH).
>
> Пользователь: Evgeny Kamenniy (gentos@inbox.ru), TZ Europe/Moscow.

---

## 1. Математика: дизпруф гипотезы о единичных расстояниях (Эрдёш)

- `ν(n)` = число пар точек на расстоянии 1 среди n точек на плоскости.
- Эрдёш 1946: `ν(n) ≤ n^{1+C/loglog n}`. Верхние границы: `O(n^{4/3})` (SST 1984), элементарная `O(n^{3/2})`.
- OpenAI: внутренняя модель ИИ улучшила **нижнюю** границу, опровергнув гипотетическую верхнюю ("unit distance conjecture").
  - Теорема 1.1: `ν(n) ≥ n^{1+δ}` бесконечно часто; `δ = 0.014` (Sawin); companion `ε ≈ 6.24×10⁻³⁸`.
  - Конструкция: CM-поле `K=L(i)`, бесконечная неразветвлённая pro-3/pro-2 башня полей классов; Голод–Шафаревич, Чеботарёв, Hajir–Maire–Ramakrishna.
- Уточнение: улучшена **нижняя** граница (не верхняя); SST 1984 — отдельная верхняя `O(n^{4/3})`. Задача Эрдёша #90, приз $500.

Ссылки:
- https://openai.com/index/model-disproves-discrete-geometry-conjecture/
- https://cdn.openai.com/pdf/74c24085-19b0-4534-9c90-465b8e29ad73/unit-distance-proof.pdf
- https://www.scientificamerican.com/article/ai-just-solved-an-80-year-old-erdos-problem-and-mathematicians-are-amazed/
- https://mathstodon.xyz/@tao/115855840223258103
- https://trotter.math.gatech.edu/papers/44.pdf

---

## 2. ИИ и кибербезопасность / геополитика

- **Mythos (Anthropic)**: red-team модель, находит уязвимости (curl/Стенберг). Спор Anthropic↔DOD предшествует Mythos и касается снятия safeguard'ов.
- **Слежка**: P-415/ECHELON, PRISM, Upstream collection, Dropmire, Fairview, JUGGERNAUT; Data Retention Directive (отменена CJEU 2014) и INDECT; Golden Shield Project. Рамка "слежка только за гражданами США" — выборочна.
- **Квантовые вычисления**: отказоустойчивых QC пока нет (только NISQ); риск сегодня — "harvest now, decrypt later". Защиту чаще ломают атакой на реализацию, а не алгоритм; атакующим может быть ИИ-агент.

---

## 3. Анализ Lua (проверка на малварь)

### Файл A — скомпилированный LuaJIT-байткод (`tural.codes.lua`)
- Путь: `K:\tural.codes\nix\scripts\tural.codes.lua`; передан через base64.
- Заголовок `1B 4C 4A 02` → LuaJIT 2.x bytecode (скомпилирован, не зашифрован).
- Первичный (ОШИБОЧНЫЙ) вердикт: "вредоносный дроппер" по `URLDownloadToFileA`+`DeleteUrlCacheEntryA`+`CreateDirectoryA`.
- ИСПРАВЛЕННЫЙ вердикт: benign. WinAPI-триада = скачивание аватарок Steam (`steamcommunity.com/profiles/%s/?xml=1` → `nix/indicminplus/%s.jpg`); Discord RPC `1088816563773259831`. Прояснены `execute_client_cmd`, clipboard, `load`.
- Для 100% доказательства: `luajit -bl`, **ljd**/**LuaJIT-Decompiler-v2** (НЕ unluac/luadec), FFI-стабы.

### Файл B — читаемый исходник "Anti Neverlose" v6.0.0
- neverlose.cc; авторы Secs#1136 & august#6530. Безопасен для хоста; единственный сетевой вызов — баннер с Discord-CDN.
- `ffi.cdef` (`CCSGOPlayerAnimationState_534535_t` и др.); `utils.opcode_scan` сигскан engine.dll/gameoverlayrenderer.dll; `ui.find`/`:override`; `vmt_hook` (offset 224); события createmove/render/aim_ack/round_start/shutdown.
- Подсистемы: antiaim_system (7 состояний, Center/Offset/Random/Spin/3-Way/5-Way, defensive_antiaim), anim-брейкеры, misc, визуалы, JSON+base64+clipboard конфиг. Остаточный риск — VAC/game-ban.

---

## 4. Кастомный резольвер для neverlose CS:GO (HVH) — главный тред

### 4.1 Реально ли?
- Технически да, но не "настоящий" нативный резольвер на Lua — только корректор-ассист поверх нативного ragebot.
- NL Lua-API даёт: FFI-чтение анимстейта (flGoalFeetYaw/flMoveYaw/flEyeYaw), entity.get_players, `aim_ack` (shot.state/hitgroup/backtrack), история по steamid, override pose/хитбоксов.
- Потолок: нет контроля над нативным резолв-пассом, нет writable-хука, данные шумные. CS:GO — legacy (CS2/Source 2 с 2023).

### 4.2 Внешний модуль?
- External (RPM/WPM): не выходит — резолв обязан попасть "внутрь тика", внешний процесс асинхронен и не переопределяет решение aimbot'а.
- Свой DLL: NL — закрытая защищённая среда, единственная точка расширения — Lua-API; сторонний хук = риск бана платформы.

### 4.3 HVH-контекст
- Нет анти-чита, нет честных игроков → опасения VAC снимаются. Резольвер — это мета.

### 4.4 Скелет resolver-ассиста
- Хранилище по steamid; классификатор AA (static/moving/jitter/spin/air по разбросу body_yaw + скорости); `aim_ack` side-flip; переключение baim/safe-point через ui.find+:override. Side-flip реально двигает угол только через FFI-запись (хрупко).

### 4.5 Накопление статистики (обучающийся резольвер)
- Многорукий бандит: корзины (класс AA × гипотеза) с hit/shot, выбор по hit-rate + доверие + exploration.
- КРИТИЧНО: фильтровать по `shot.state` — промахи spread/prediction/hitchance НЕ винить в резолве.
- Персистентность (`database.read/write`), decay старых наблюдений (~0.9/раунд), anti-bruteforce.

### 4.6 Локальная LLM?
- LLM конкретно — не тот инструмент (форма задачи + латентность + некуда встроить). Лёгкий ML да: обучение офлайн → дистилляция в Lua-инференс (логрегрессия/MLP/boosting/крошечный LSTM). Метки — из hit/miss статистики. В HVH онлайн-бандит с decay обычно практичнее.

### 4.7 Железо
- Бандит/Lua-MLP-инференс — почти ноль. Офлайн-тренировка — обычный CPU, без GPU. Мощное железо — только под локальную LLM (неподходящий путь). Горлышко — данные/API, не вычисления.

### 4.8 Тикрейт
- Важен: 128 tick = вдвое больше данных, быстрее AA, defensive-детект и DT завязаны на tickinterval. Писать tick-agnostic: окна/пороги/decay в секундах, тики через `globals.tickinterval`. Не смешивать 64/128 датасеты.

### 4.9 Тип оружия
- На резолв (угол) не влияет; на стратегию — сильно. Скаут: голова = ванщот, body не убивает фуллхп → baim-фоллбэк бесполезен (safe-point head/скип). AWP/авто: body летален. DT на скауте — для тайминга (обход defensive/пиков), связка Hide Shots + DT + safe-point head.

### 4.10 Body-shot при низком HP
- Критерий динамический: "добьёт ли body-урон текущее HP". Скаут: грудь ~88, живот ×1.25 ~110; против ≤~85–90 HP body = килл. Резольвер сам переключается на baim при низком HP. В ML — HP/броня как признак.

### 4.11 Прострел стен (autowall)
- Урон по хитбоксу — живой autowall-расчёт (обёртка над нативным), а не таблица. Выбор хитбокса = лучший летальный по простреливаемости: голова → грудь/живот → скип.
- autowall считается по зарезолвленной позиции → наследует качество резолва. Ограничения: стоимость трасс (кэш), min-damage от autowall, материал/многослойность. В ML: autowall-урон по голове/телу, флаг "за кавером", число пробитий.

### Сложившаяся архитектура
Классификатор AA → бандит со статистикой и decay → weapon/HP/autowall выбор хитбокса, поверх нативного ragebot через ui.find/:override + (опционально) FFI-запись угла. Открытый следующий шаг: связный скелет-модуль.

---

*Сохранено автоматически из сессии Notion AI.*
