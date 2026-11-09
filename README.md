# НГУ AI Hackathon — модуль 1

Запуск готового агента openJiuwen в условиях конкурса: прокси, штатные инструменты, общий бюджет, запись ответов.

- `docs/rules.md` — правила и открытые вопросы (AGE-5)
- `docs/gaps.md` — что берём готовым, что настраиваем, где адаптер (AGE-22)
- `docs/interfaces.md` — стыки модулей

## Сборка и запуск

```bash
docker build -t hack:latest .
```

Запуск — командой из `docs/rules.md`. Нужны `LLM_BASE_URL` и `LLM_API_KEY`; `BUDGET` необязателен, по умолчанию 100000.

## Проверка без ключа

`evaluation/mock_llm.py` заменяет прокси и записывает всё, что отправляет фреймворк. `evaluation/spike_oj.py` сравнивает конфигурации агента, `evaluation/check_limits.py` показывает, что реально блокируют штатные ограничения.

Расход и итоги пишутся в stderr и в `/tmp/harness/trajectory.jsonl`.
