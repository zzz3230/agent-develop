# Выбор и проверка выпускной версии (12 ноября)

Все команды — из корня проекта в PowerShell. Результаты складываются в `benchmark-runs\` (в git не попадает), итог выбора — в `docs\release\` (коммитится).

## Что есть в коде

| Файл | Зачем |
|---|---|
| `evaluation/run_image.py` | запуск образа с флагами конкурса (read-only корень, `/tmp` 2g, 8 CPU, 16g, 512 pids, `HOME=/tmp`), копия задач без эталонов, журнал в `RUN\harness`, предел времени 3600 с, `--hard-budget` (убивает контейнер при достижении расхода — как прокси), `--mock`, сразу проверка через `evaluation.grade` |
| `evaluation/container_probe.py` | запускается внутри любого образа: read-only, cgroup CPU/RAM/pids, что лежит в образе, модель и лимиты |
| `evaluation/check_image.py` | отчёт по образу: раздел «Mock» и раздел «Настоящий прокси» отдельно |
| `evaluation/select_release.py` | выбор основной и резервной версии по правилу «максимум баллов, при равенстве меньший расход» |
| `RUN_TIME_LIMIT` | переменная только для проверки остановки по времени; может лишь уменьшить 3300 с |

## 0. Подготовка (бесплатно, заранее)

```powershell
docker build -t hack:latest .
git worktree add ..\agent-prev 273888c
docker build -t hack:prev ..\agent-prev
python benchmarks/diverse-v1/suite.py prepare --split holdout --order-seed 101 --out benchmark-runs\holdout-input
python -m evaluation.check_image --image hack:latest --out benchmark-runs\check-latest-mock
python -m evaluation.check_image --image hack:prev --out benchmark-runs\check-prev-mock
```

`check_image` без `--real` не тратит бюджет (5–10 минут). Ждём 0 критических провалов в `benchmark-runs\check-...\report.md`.

## 1. Сравнение на отложенном наборе (платно)

Ключ только в переменной окружения текущего окна, в файлы он не пишется:

```powershell
$env:LLM_BASE_URL = "https://api.neuraldeep.tech/v1"
$env:LLM_API_KEY = "sk-..."
```

Одинаковый бюджет для всех: 24 задачи из 100 → `24000` (и как оценка агента `BUDGET`, и как жёсткий предел).

```powershell
python -m evaluation.run_image --image hack:latest --label new --tasks benchmark-runs\holdout-input\tasks --references benchmarks/diverse-v1 --env BUDGET=24000 --hard-budget 24000 --out benchmark-runs\h-new
python -m evaluation.run_image --image hack:prev --commit 273888c --label prev --tasks benchmark-runs\holdout-input\tasks --references benchmarks/diverse-v1 --env BUDGET=24000 --hard-budget 24000 --out benchmark-runs\h-prev
```

Необязательно (только если бюджет позволяет): тот же образ без очереди, `--env QUEUE=0 --label noqueue --out benchmark-runs\h-noqueue`. Если победит он, `QUEUE=0` придётся сделать значением по умолчанию и пересобрать образ — об этом предупредит отчёт выбора.

Каждый прогон печатает таблицу по задачам и строку «Итого», сохраняет `graded.json` и `run.json`. Необязательные эксперименты не ждём.

## 2. Выбор и фиксация

```powershell
python -m evaluation.select_release --out docs\release --tag new=benchmark-runs\h-new prev=benchmark-runs\h-prev
```

Скрипт откажется сравнивать прогоны с разными задачами или разным `--hard-budget`. Он пишет `docs\release\selection.md/json` (commit, id образа, модель, лимиты попыток, лимит времени, флаги) и ставит теги `hack:release` и `hack:backup` (резерв — следующий по баллам, по возможности другой образ). Затем:

```powershell
copy benchmark-runs\h-new\graded.json docs\release\holdout-new.json
copy benchmark-runs\h-prev\graded.json docs\release\holdout-prev.json
git add docs/release
git commit -m "Release selection 2026-11-12"
git tag release-2026-11-12 <commit основной версии из selection.md>
```

После этого — только критические исправления; после каждого снова шаг 3.

## 3. Проверка выбранного образа

```powershell
python -m evaluation.check_image --image hack:release --out benchmark-runs\check-release --real
python -m evaluation.check_image --image hack:backup --out benchmark-runs\check-backup
```

Раздел «Mock» (бесплатно): песочница, 100 задач в очереди, остановка при отказе прокси, остановка по времени (`RUN_TIME_LIMIT=20`), убийство контейнера посреди работы (ответы на диске целые), жёсткий бюджет. Это проверка механики, не качества.

Раздел «Настоящий прокси» (`--real`, около 10000 единиц): 4 пары официальных примеров (math 0000/0004, data 0002/0006, search 0001/0005, coding 0003/0007), обе задачи пары должны быть верны. Отложенный набор уже прогнан на этом образе в шаге 1; повторять нужно, только если образ пересобирался: добавьте `--holdout benchmark-runs\holdout-input\tasks --hard-budget 24000`.

Полный платный прогон на 100 задач — только если на ключе есть бюджет; он запускается так же через `run_image` без `--hard-budget`.

## Если проверка провалилась

`check_image` завершается с кодом 1 и строками «ПРОВАЛ» в `report.md`. Чиним, если это критично и быстро; иначе сдаём `hack:backup`, предварительно проверив его той же командой с `--real`.
