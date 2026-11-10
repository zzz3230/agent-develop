# A/B: инструкция экономить токены

10 ноября 2026. 160 реальных попыток: 8 задач × 10 повторов × 2 варианта инструкции. В каждой паре одна задача и один раунд; порядок вариантов случайный. Baseline запущен заново, результаты прошлой серии не подставлялись в контрольную группу.

Модель qwen3.8-27b-noreason, один короткий штатный bash, ReActAgent OJ 0.1.19, temperature=0, 6 шагов, max_output=1200, таймаут 150 с. Каждая попытка имеет отдельные файлы и conversation_id. Общие правила формата ответа в обоих вариантах одинаковы. Меняется только инструкция о способе работы и экономии.

expected остаётся снаружи контейнера, check сохранён. Для coding отдельно запущены исходные тесты и проверена их сохранность. Стоимость — полный usage input/10 + output без скидок кеша. Цена более длинной инструкции включена в расход.

| Тип | Baseline: правильно | Economy: правильно | Средний расход baseline | Средний расход economy | Экономия | Запросов baseline / economy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| math | 20/20 | 20/20 | 194.95 | 193.88 | 0.55% | 40 / 40 |
| data_analysis | 20/20 | 20/20 | 294.62 | 282.44 | 4.13% | 53 / 50 |
| search | 20/20 | 20/20 | 357.0 | 361.67 | -1.31% | 74 / 71 |
| coding | 20/20 | 20/20 | 639.5 | 577.82 | 9.64% | 93 / 80 |
| all | 80/80 | 80/80 | 371.51 | 353.95 | 4.73% | 260 / 241 |

Положительная экономия означает меньший расход у economy; отрицательная — увеличение.

## Точные инструкции

### Baseline

```text
Solve the task with the tools in as few steps as possible. Your last message must be only the final answer on one line, without explanation, labels, Markdown, or code fences. For a numeric answer, return only the number. For code repair, return DONE after running the tests. Return IMPOSSIBLE if the data cannot give an exact answer. Do not create answer.txt.
```

### Economy

```text
Solve correctly while minimizing total token usage. Combine related operations into one tool call when practical. Print only the tool output needed to solve the task. Avoid repeating successful computations. For code repairs, run the tests after editing. Your last message must be only the final answer on one line, without explanation, labels, Markdown, or code fences. For a numeric answer, return only the number. For code repair, return DONE after running the tests. Return IMPOSSIBLE if the data cannot give an exact answer. Do not create answer.txt.
```

## Ошибки

В этой серии ошибок нет.

## Вывод

Economy снизил суммарный расход с 29721.2 до 28316.1, на 4.73%,
при одинаковых 80/80. Запросов стало 241 вместо 260. Наибольший эффект
в coding: 639.5 → 577.82 в среднем (-9.64%), 93 → 80 запросов,
суммарное время 176.6 → 121.4 с. В CSV наблюдаемая экономия 4.13%,
в math 0.55%; search стал дороже на 1.31%.

Математика и поиск не дают убедительного повода менять инструкцию по
этим данным. Для отложенной проверки прежде всего стоит взять экономную
инструкцию в coding. Разницу на двух задачах нельзя считать устойчивым
эффектом на всём типе. Production-промпт не заменён.

## Ограничения

По две разные задачи на тип; повторы проверяют стабильность на этих условиях, а не обобщение на финальные задачи. Различия формулировок и сложности могут изменить эффект инструкции. Профиль не менялся по результатам промежуточных запусков. Рабочий промпт автоматически не заменён.

Всего 501 запросов, стоимость 58037.3; оценочный usage у 0 попыток.

Артефакты: C:\Users\hilis\hackathon-task\model-comparison\prompt-ab (results.jsonl, usage.jsonl, graded.json, console.log и рабочие файлы).
