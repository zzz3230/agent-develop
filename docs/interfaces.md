# Стыки модулей (AGE-22, черновик)

Родные объекты OJ используем напрямую. Общие типы только там, где их нет. Подтвердить втроём.

| Стык | Где | Что |
| --- | --- | --- |
| Task | `runtime/tasks.py` | `id`, `type`, `instruction`, `reward`, `dir`, `cwd`, `query`; эталонов нет |
| Сохранение | `runtime/tasks.py: save_answer` | только М1, только при статусе `solved` |
| Бюджет | `runtime/budget.py: Budget` | `remaining()`, `begin_task(id, limit)`, `end_task()` возвращает расход задачи |
| Агент | `runtime/oj_agent.py: react_agent` | модель, папка, штатные инструменты, число шагов |
| Журнал | `runtime/budget.py: Journal` | JSONL: `llm_call`, `outcome`, `finish` |

## Куда подключаются М2 и М3

- **М2:** в `run_agent.py` константы `TOOLS`, `MODEL`, текст `SYSTEM` в `runtime/oj_agent.py`, разбор итогового ответа в `attempt`.
- **М3:** цикл `for task in tasks` в `run_agent.py: run`. Сейчас порядок по имени каталога; сюда встаёт выбор `Decision` (задача, модель, лимиты). Данные для оценки — события журнала.

Отчёт о попытке сейчас: `status` (`solved`, `impossible`, `failed`), `detail`, `cost`. Статус `solved` не означает, что скрытые тесты пройдены.
