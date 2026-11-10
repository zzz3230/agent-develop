# Стыки модулей (AGE-22, черновик)

Родные объекты OJ используем напрямую. Общие типы только там, где их нет. Подтвердить втроём.

| Стык | Где | Что |
| --- | --- | --- |
| Task | `runtime/tasks.py` | `id`, `type`, `instruction`, `reward`, `dir`, `cwd`, `query`; эталонов нет |
| Сохранение | `runtime/tasks.py: save_answer` | только М1, только при статусе `solved` |
| Бюджет | `runtime/budget.py: Budget` | `remaining()`, `begin_task(id, limit)`, `end_task()` возвращает расход задачи |
| Агент | `runtime/oj_agent.py: react_agent` | модель, папка, штатные инструменты, число шагов |
| Журнал | `runtime/budget.py: Journal` | JSONL: `llm_call`, `outcome`, `finish` |
| Лимиты попытки | `runtime/attempt_policy.py` | `AttemptLimits`, `limits_for_task(type)`; М3 может передать профиль в `attempt` |

Актуальное состояние М2 описано в `age-13-23.md`: CSV_SCHEMA и SEARCH_CONTEXT
включены по умолчанию. `attempt(..., limits=None, timeout=None)` принимает
профиль и остаток общего времени. Причина локальной остановки попадает в
outcome, лимиты — в attempt_start. Лимиты одной задачи не считаются отказом API.

## Куда подключаются М2 и М3

- **М2:** в `run_agent.py` константы `TOOLS`, `MODEL` и разбор ответа в `attempt`; инструкции выбираются через `runtime/profiles.py: system_for_task`. Только coding получает economy; остальные типы — baseline. Фабрика `react_agent` принимает необязательный `system_prompt`; старые вызовы совместимы.
- **М3:** цикл `for task in tasks` в `run_agent.py: run`. Сейчас порядок по имени каталога; сюда встаёт выбор `Decision` (задача, модель, лимиты). Данные для оценки — события журнала.

Отчёт о попытке сейчас: `status` (`solved`, `impossible`, `failed`), `detail`, `cost`. Статус `solved` не означает, что скрытые тесты пройдены.
