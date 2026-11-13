"""Publish quality-only training and the two single-trial held-out runs."""
import json
from pathlib import Path

from evaluation.quality_dataset import ROOT,META,WORK,dump
from evaluation.quality_experiment import MODES,REPORT,freeze


def publish():
    rows=json.loads((WORK/'comparison/results.json').read_text(encoding='utf-8'))
    assert len(rows)==2 and {r['mode'] for r in rows}==set(MODES)
    protocol=json.loads((WORK/'comparison/protocol.json').read_text(encoding='utf-8'))
    assert freeze()==protocol['model_hashes']
    split=json.loads((META/'manifest.json').read_text(encoding='utf-8'))
    train={r['group'] for r in split['tasks'] if r['split']=='train'}
    test=json.loads((ROOT/'benchmarks/quality-holdout-200/manifest.json').read_text(encoding='utf-8'))
    assert not train&{r['group'] for r in test['tasks']}
    details={};orders=[]
    for row in rows:
        target=WORK/'comparison'/row['mode']
        info=json.loads((target/'run.json').read_text(encoding='utf-8'))
        grade=json.loads((target/'graded.json').read_text(encoding='utf-8'))
        events=[json.loads(s) for s in (target/'harness/trajectory.jsonl').read_text(encoding='utf-8').splitlines()]
        orders.append([e['task'] for e in events if e['event']=='queue_pick'])
        details[row['mode']]=dict(image_id=info['image_id'],commit=info['commit'],env=info['env'],
            started=info['started'],by_type=grade['by_type'],false_claims=grade['total']['false_claims'],
            predictor_init=next(e for e in events if e['event']=='predictor_init'),
            resource_sampling_errors=info['resource_sampling_errors'])
    prefix=0
    for a,b in zip(*orders):
        if a!=b:break
        prefix+=1
    best=max(rows,key=lambda r:(r['strict_points'],-r['spent']))
    no_words=next(r for r in rows if r['mode']=='quality_minilm_structural')
    words=next(r for r in rows if r['mode']=='quality_minilm_keywords')
    delta=no_words['strict_points']-words['strict_points']
    training=json.loads((REPORT/'training.json').read_text(encoding='utf-8'))
    validation=json.loads((REPORT/'holdout-metrics.json').read_text(encoding='utf-8'))
    collection=json.loads((REPORT/'collection.json').read_text(encoding='utf-8'))
    candidate=json.loads((WORK/'candidate.json').read_text(encoding='utf-8'))
    report=dict(protocol=protocol,results=rows,details=details,best_observed=best,
        no_keywords_minus_keywords=delta,order_common_prefix=prefix,
        order_common_tasks=len(set(orders[0])&set(orders[1])),training=training,
        source_holdout=validation,candidate=candidate,model_freeze=json.loads((WORK/'frozen-models.json').read_text(encoding='utf-8')),
        known_charged_tokens=round(sum(r['spent'] for r in rows)+collection['spent'],1))
    dump(REPORT/'comparison.json',report)
    lines=['# MiniLM на качественных примерах: с ключевыми словами и без','',
        'Оба варианта обучены заново на 88 задачах из diverse-v1, gaps-v1 и tricks-v1. '
        'Старый benchmark100 не использован. Источники обучения: 39 diverse, 31 gaps, 18 tricks; '
        '74 успешных попытки из 88. Ещё 44 исходные задачи отложены. '
        'Из их 39 групп созданы новые 200 экземпляров: 160 выполнимых и 40 невыполнимых, '
        f"максимум {words['possible']:g} баллов. Группы обучения и проверки не пересекаются.",'',
        '108 совместимых исторических измерений переиспользованы; 24 недостающих diverse holdout '
        'пройдены на f8e23ac после фиксации моделей: 18 правильных решений, 14841.3 токена. '
        'Исходные тесты и их результаты уже известны команде, поэтому оценка не является слепой внешней проверкой. '
        'Очевидные алгоритмические повторы объединены, полной семантической независимости это не гарантирует.','',
        'В обоих вариантах одинаковый MiniLM INT8 (384 числа) и одинаковые линейные головы. '
        'С ключевыми словами — 45 обычных признаков и всего 429 чисел; без — 18 обычных признаков '
        'и всего 402. Из структурного варианта удалены также счётчики assert/test_ в коде. '
        'Слова остаются частью текста для энкодера: отключены именно ручные счётчики ключевых слов. '
        'Нормализация и выбор C/alpha выполнены только на пяти обучающих группах. '
        'В обоих случаях выбраны C=0.0001 и Ridge alpha=10000. После проверки модели не менялись.','',
        '## Реальный прогон 200/50к','',
        'По одному последовательному прогону. Одинаковые входы, награды, порядок каталогов, '
        'модель qwen3.8-27b-noreason, инструменты, лимиты попыток, жадный алгоритм и SCORE_ALPHA=1. '
        'Основные баллы и правильные решения включают только попытки, завершённые до пересечения '
        '50000 взвешенных токенов (вход/10 + выход). Небольшое превышение последним запросом '
        'отражено в фактическом расходе.','',
        '| Вариант | Баллы до 50к | Правильных до 50к | Полные баллы | Расход | Время, мин |',
        '|---|---:|---:|---:|---:|---:|']
    for label,r in [('MiniLM + признаки без ключевых слов',no_words),('MiniLM + признаки с ключевыми словами',words)]:
        lines.append(f"| {label} | {r['strict_points']:g} | {r['strict_correct']} | {r['points']:g} | {r['spent']:.1f} | {r['seconds']/60:.1f} |")
    best_label='без ключевых слов' if best['mode'].endswith('structural') else 'с ключевыми словами'
    lines+=['',f"Лучшее наблюдение: вариант {best_label}. Разница без ключевых слов минус с ключевыми: "
        f"{delta:+g} баллов. Первые {prefix} выбранных задач совпали; пересечение наборов попыток — "
        f"{report['order_common_tasks']}. Один прогон и похожие очереди не доказывают устойчивого "
        'преимущества: ответы модели и фактические стоимости попыток также варьируются.','',
        'Результат 459 баллов старого MiniLM получен на других 200 задачах (максимум 852), '
        'поэтому напрямую сравнивать с ним баллы этой таблицы нельзя. '
        'В этом эксперименте отдельно не измерялся эффект замены обучающего набора: '
        'для этого старую модель нужно проверить на тех же новых входах.','',
        '## Предикторы на 44 исходных отложенных задачах','',
        'Успешность почти постоянна: диапазон прогнозов примерно 83.4–84.7%, '
        f"фактически правильных {validation['correct']} из 44. Brier около 0.2267 у обоих "
        'вариантов и у постоянного прогноза по обучающей доле успеха. '
        'Средняя абсолютная ошибка стоимости около 470 токенов против 494 у постоянной '
        'обучающей средней. Низкая ошибка на обучающих фолдах не означает улучшения на закрытых задачах. '
        'Отложенные метрики не использованы для перенастройки моделей.','',
        '## Файлы и воспроизведение','',
        'Разбиение и инструкции: benchmarks/quality-minilm/README.md; готовые входы: '
        'benchmarks/quality-holdout-200. Компактная разметка: cached-labels.json и new-labels.json; '
        'обучение: training-data.json и training.json; независимые от подбора метрики: '
        'holdout-metrics.json; протокол, хеши, результаты и происхождение образа: comparison.json. '
        'Сырые журналы остаются в benchmark-runs/quality-minilm-v1 (исключены из Git). '
        'Эталоны и разметка не попадают в образ агента. Все 40 решаемых эталонных исправлений '
        'нового набора прошли публичные и скрытые проверки в Docker без сети. '
        'По умолчанию конкурсный агент не переключается на новые головы автоматически.','']
    (REPORT/'README.md').write_bytes(('\n'.join(lines).rstrip()+'\n').encode('utf-8'))
    print(json.dumps(dict(best=best['mode'],no_keywords=no_words['strict_points'],keywords=words['strict_points'],delta=delta)),flush=True)


if __name__=='__main__':publish()
