# Проверяющий: правильность, reward, расход

Одна команда считает по каждой задаче правильность, баллы, расход и время и выдаёт общий итог.

```powershell
python -m evaluation.grade --references benchmarks/diverse-v1 --run RUN\tasks --trajectory RUN\harness\trajectory.jsonl --docker hack:latest --json RUN\graded.json
```

`evaluation.run_image` вызывает его сам после прогона, отдельно запускать нужно только для старых папок.

## Правила сравнения

| Тип ответа | Метрика | Правило |
|---|---|---|
| целое число (math, data) | `exact_int` | пробелы по краям убираются, ответ целиком `[+-]?цифры`, сравнение как чисел |
| строка (search и др.) | `exact_str` | только `strip` + регистр, как сказали организаторы («strip lowercase»); внутренние пробелы и пунктуацию не трогаем |
| coding | `unittest` | исходные тесты задачи восстанавливаются из эталона (правка тестов агентом не помогает), плюс скрытые тесты; нужно `Ran N>0` и `OK`; с `--docker` — в образе без сети |
| невыполнимая | `unavailable` | верно только `IMPOSSIBLE`; любой другой ответ — ложный |

Метрики — подклассы `Metric` из OpenJiuwen (`openjiuwen.agent_evolving.evaluator.metrics.base`); если пакет на машине не стоит, используется совместимая заглушка.

Эталоны берутся только из `--references` на хосте. В контейнер агента монтируется копия задач без `expected`; `run_image` отказывается запускаться, если во входной папке есть `answer.json`, `manifest.json` или `test_private*`.

`solved` в журнале не считается правильностью: столбец «Журнал» показан рядом, а в итоге отдельно — сколько раз агент написал `solved`, но ответ неверен.

## Поддерживаемые эталоны

- `benchmarks/diverse-v1` (64 задачи, `suite.py prepare` готовит вход агента);
- наборы `evaluation/build_suite.py` (`manifest.json` + `references/`);
- примеры организаторов `evaluation/fixtures/tasks` с `--private evaluation/fixtures/private_checks`.

Тесты проверяющего: `python -m unittest evaluation.test_grade`.
