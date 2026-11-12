"""Publish the completed single-trial 200-task predictor/policy comparison."""
import argparse
import json
import math
import re
from pathlib import Path

from evaluation.compare_pool_predictors import MODES

LABELS={
    'numeric':'Признаки с ключевыми словами',
    'structural':'Признаки без ключевых слов',
    'embedding':'MiniLM + признаки',
    'strong_embedding':'Только BGE',
    'bge_structural':'BGE + признаки без ключевых слов',
    'bge_keywords':'BGE + все признаки',
}


def memory_mib(sample):
    match=re.match(r'([\d.]+)([A-Za-z]+)',sample.get('MemUsage',''))
    units={'B':1,'kB':1000,'KB':1000,'KiB':1024,'MB':1000000,'MiB':1048576,'GB':1000000000,'GiB':1073741824}
    return float(match[1])*units[match[2]]/1048576 if match else 0


def publish(source,out):
    rows=json.loads((source/'comparison.json').read_text(encoding='utf-8'))
    protocol=json.loads((source/'protocol.json').read_text(encoding='utf-8'))
    selection=json.loads((source/'selection.json').read_text(encoding='utf-8'))
    greedy=[r for r in rows if r['policy']=='greedy']
    assert len(greedy)==6 and {r['mode'] for r in greedy}==set(MODES)
    best=selection['best'];knapsacks=[r for r in rows if r['policy']=='knapsack']
    assert len(knapsacks)==1 and knapsacks[0]['mode']==best['mode']
    knapsack=knapsacks[0];details={};traces={};grades={}
    for row in rows:
        name=row['mode']+'-'+row['policy'];target=source/name
        grade=json.loads((target/'graded.json').read_text(encoding='utf-8'))
        grades[name]=grade
        info=json.loads((target/'run.json').read_text(encoding='utf-8'))
        events=[json.loads(s) for s in (target/'harness/trajectory.jsonl').read_text(encoding='utf-8').splitlines()]
        traces[name]=events
        predictions=[e for e in events if e['event']=='prediction']
        plans=[e for e in events if e['event']=='knapsack_plan']
        details[name]=dict(image_id=info['image_id'],started=info['started'],env=info['env'],
            by_type=grade['by_type'],false_claims=grade['total']['false_claims'],
            predictor_init=next((e for e in events if e['event']=='predictor_init'),None),
            predicted_total_cost=sum(e['cost'] for e in predictions),
            first_plan=dict(selected=len(plans[0]['selected']),remaining=plans[0]['remaining'],
                            seconds=plans[0]['seconds']) if plans else None,
            planning_seconds=sum(e['seconds'] for e in plans),plan_count=len(plans),
            max_sampled_memory_mib=round(max((memory_mib(s) for s in info['resource_samples']),default=0),1),
            hard_limits={k:info.get('probe',{}).get(k) for k in ('cpus','memory_bytes','pids_max','tmp_bytes')},
            resource_sampling_errors=info['resource_sampling_errors'])
    failures=[]
    failed_root=source.parent/'pool200-infrastructure-failures'
    if failed_root.exists():
        for path in failed_root.glob('*/graded.json'):
            g=json.loads(path.read_text(encoding='utf-8'))
            failures.append(dict(name=path.parent.name,spent=g['spent'],excluded=True,
                                 reason='Docker/WSL unexpected EOF; incomplete trial'))
    pair=[traces[best['mode']+'-'+policy] for policy in ('greedy','knapsack')]
    predictions=[{e['task']:(e['p'],e['cost']) for e in events if e['event']=='prediction'} for events in pair]
    assert predictions[0].keys()==predictions[1].keys() and len(predictions[0])==200
    assert all(math.isclose(a,b,rel_tol=1e-7,abs_tol=1e-7) for task,values in predictions[0].items()
               for a,b in zip(values,predictions[1][task])),'Policy trials used different predictions'
    orders=[[e['task'] for e in events if e['event']=='queue_pick'] for events in pair]
    prefix=0
    for a,b in zip(*orders):
        if a!=b:break
        prefix+=1
    policy_order=dict(common_prefix=prefix,common_tasks=len(set(orders[0])&set(orders[1])),
        greedy_only=sorted(set(orders[0])-set(orders[1])),knapsack_only=sorted(set(orders[1])-set(orders[0])),
        predictions_equal=True)
    common=set(orders[0])&set(orders[1]);breakdown={}
    for policy,events in zip(('greedy','knapsack'),pair):
        spent=0.;eligible=set()
        for event in events:
            if event['event']=='llm_call':spent+=event['cost']
            elif event['event']=='outcome' and spent<=protocol['budget']+1e-6:eligible.add(event['task'])
        scored=grades[best['mode']+'-'+policy]['rows']
        breakdown[policy]=dict(common_points=sum(r['points'] for r in scored if r['id'] in common&eligible),
            exclusive_points=sum(r['points'] for r in scored if r['id'] in eligible-common))
    policy_order['score_breakdown']=breakdown
    report=dict(protocol=protocol,selection=selection,results=rows,details=details,policy_order=policy_order,
                excluded_runs=failures,charged_completed_trials=round(sum(r['spent'] for r in rows),1),
                charged_including_failed_trials=round(sum(r['spent'] for r in rows)+sum(r['spent'] for r in failures),1))
    out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 200 задач, бюджет 50 000: предикторы и рюкзак','',
        'Один полный прогон каждого обученного варианта. Одинаковые 200 задач оценочной части '
        'planner-500: по 50 каждого типа, 40 невыполнимых, 160 выполнимых, максимум 852 балла. '
        'Награды 1–10 назначены независимо от содержимого. Модель qwen3.8-27b-noreason, '
        'alpha 1, повторные попытки выключены; решатель, инструменты и лимиты попыток одинаковые.','',
        'Основной результат — только проверенные ответы с завершением попытки до пересечения '
        '50 000 списанных взвешенных токенов (вход / 10 + выход). Ответ ровно на границе учитывается. '
        'Монитор может остановить контейнер после последнего запроса с небольшим превышением: '
        'поэтому отдельно сохранены полный результат и фактический расход.','',
        '| Предиктор, жадный алгоритм | Баллы до 50к | Правильных до 50к | Полные баллы | Расход | Время, мин |',
        '|---|---:|---:|---:|---:|---:|']
    for r in sorted(greedy,key=lambda r:r['strict_points'],reverse=True):
        lines.append(f"| {LABELS[r['mode']]} | {r['strict_points']:g} | {r['strict_correct']} | {r['points']:g} | {r['spent']:.1f} | {r['seconds']/60:.1f} |")
    delta=knapsack['strict_points']-best['strict_points']
    lines+=['',f"Выбран {LABELS[best['mode']]}: {best['strict_points']:g} баллов. "
        f"С тем же предиктором рюкзак получил {knapsack['strict_points']:g} баллов "
        f"до границы; правильных решений: {knapsack['strict_correct']}. "
        f"Разница рюкзак минус жадный: {delta:+g} баллов ({delta/best['strict_points']*100:+.1f}%). "
        f"Фактический расход рюкзака {knapsack['spent']:.1f}, время {knapsack['seconds']/60:.1f} мин.",'',
        'Рюкзак использует reward × p и прогнозируемую стоимость; он перестраивает план после попыток. '
        'Параметры alpha и моделей на этих 200 задачах не подбирались. Выбор лучшего предиктора '
        'и сравнение политик выполнены на одной выборке: результат выбора может быть оптимистичен. '
        'Один прогон не устанавливает устойчивого превосходства.','',
        'Набор исправлен до запуска сравнения: дополнительная математическая цель q + offset '
        'теперь видна агенту. Старый остановленный прогон на 500 задачах не используется ни для '
        'обучения, ни для выбора победителя. Коэффициенты всех моделей обучены заранее и не менялись.','',
        'Дополнительная исходная очередь прервалась при сбое Docker/WSL на 30692.2 токена и '
        'исключена. Неудачная параллельная подготовка BGE без признаков не сделала ни одного '
        'LLM-вызова. После восстановления Docker оставшиеся полноценные прогоны шли последовательно. '
        'Завершённые обученные варианты не перезапускались. Аварийные расходы сохранены отдельно.','',
        'Входы и эталоны отделены: в контейнер попадает только input. Разбиение по исходным семействам '
        'не доказывает семантической независимости, а сами gaps/tricks уже известны команде. '
        'Это диагностическая оценка планирования при дефиците бюджета, не прогноз закрытого конкурса.','',
        'Протокол, хеш входов/моделей, расход каждого варианта и подробности планирования — '
        'в results.json. Сырые журналы: benchmark-runs/pool200-budget50000 (исключены из Git). '
        'Воспроизведение: подготовить исправленную eval-нагрузку на 200 задач с seed 101/1001, '
        'собрать образ с предикторами и выполнить `python -m evaluation.compare_pool_predictors`. '
        'По умолчанию агент и планировщик не переключаются на победителя автоматически.','']
    first=details[best['mode']+'-knapsack']['first_plan']
    if first:lines.insert(-1,f"Первый план рюкзака: {first['selected']} из 200 задач, построение {first['seconds']:.6f} с.\n")
    lines.insert(-1,f"Первые {prefix} задач выбраны в одинаковом порядке; пересечение выбранных задач — "
        f"{policy_order['common_tasks']}. Баллы на общих задачах: жадный {breakdown['greedy']['common_points']:g}, "
        f"рюкзак {breakdown['knapsack']['common_points']:g}; дополнительные баллы на остальных задачах: "
        f"{breakdown['greedy']['exclusive_points']:g} и {breakdown['knapsack']['exclusive_points']:g}. "
        "Поэтому разницу одного прогона нельзя полностью приписать политике: ответы модели и фактическая "
        "стоимость попыток также различаются.\n")
    (out/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(best=best['mode'],greedy=best['strict_points'],knapsack=knapsack['strict_points'],delta=delta)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('benchmark-runs/pool200-budget50000'))
    p.add_argument('--out',type=Path,default=Path('docs/results/pool200-50k-v1'));a=p.parse_args();publish(a.source,a.out)
