"""Compare the first seed of all six variants; preserve and account for unused repeats."""
import hashlib
import json
from pathlib import Path
import subprocess

from evaluation.predictor_experiment import ROOT,OUT,dump
from evaluation.report_predictors import memory_bytes
from evaluation.audit_usage import audit


def events(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def main():
    prior=ROOT/'docs/results/offline-predictors-v1/results.json'
    original=json.loads(prior.read_text(encoding='utf-8'))
    result=dict(seed=101,budget=12000,possible_points=119,
        prior_result_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
        runs=[r for r in original['runs'] if r['seed']==101],
        encoder_probe=json.loads((OUT/'bge-resource-probe.json').read_text(encoding='utf-8')),
        training={},images={},sources={})
    for label in ('extensions','combined'):
        report=json.loads((OUT/f'training_report_{label}.json').read_text(encoding='utf-8'))
        assert report['training_sha256']==original['training']['training_sha256']
        result['training'][label]=report
    groups=[('structural',OUT/'extensions/structural-101','agent-develop:predictor-extensions','strong_embedding'),
            ('strong_embedding',OUT/'extensions/strong_embedding-101','agent-develop:predictor-extensions','strong_embedding'),
            ('bge_structural',OUT/'combined-101','agent-develop:predictor-combined','bge_structural')]
    for mode,directory,image,commit_model in groups:
        info=json.loads((directory/'run.json').read_text(encoding='utf-8'))
        graded=json.loads((directory/'graded.json').read_text(encoding='utf-8'))
        assert all(r['answer']=='DONE' for r in graded['rows'] if r['correct'] and r['type']=='coding')
        es=events(directory/'harness/trajectory.jsonl');calls=[e for e in es if e['event']=='llm_call']
        a=audit(directory/'console.log')
        samples=[memory_bytes(s['MemUsage'].split('/')[0]) for s in info['resource_samples']]
        commit=subprocess.check_output(['git','log','-1','--format=%H','--',f'predictors/{commit_model}.json'],cwd=ROOT,text=True).strip()
        row=dict(mode=mode,seed=101,points=graded['total']['points'],correct=graded['total']['correct'],spent=graded['spent'],
            seconds=info['wall_seconds'],image_id=info['image_id'],agent_commit=commit,
            prediction_init_seconds=next(e['seconds'] for e in es if e['event']=='predictor_init'),
            sampled_peak_memory_bytes=max((s for s in samples if s is not None),default=0),
            usage_audit=a,calls=len(calls),estimated_calls=sum(bool(e.get('estimated')) for e in calls),
            resource_sampling_errors=info.get('resource_sampling_errors',[]),budget_overrun=round(graded['spent']-12000,1))
        row['proxy_reported_weighted_tokens']=round(graded['spent']-a['extra_cost'],1) if len(calls)==a['responses'] and not row['estimated_calls'] else None
        assert row['seconds']<3600 and row['sampled_peak_memory_bytes']<16*1024**3
        result['runs'].append(row)
        if image not in result['images']:
            image_info=json.loads(subprocess.check_output(['docker','image','inspect',image],text=True))[0]
            assert image_info['Size']<4_000_000_000
            result['images'][image]=dict(id=image_info['Id'],bytes=image_info['Size'])
            program="import hashlib,json;from pathlib import Path;r=Path('/app');fs=[r/'run_agent.py',*sorted((r/'runtime').glob('*.py')),*sorted((r/'predictors').glob('*.json'))];print(json.dumps({p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest() for p in fs}))"
            hashes=json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--entrypoint','python',image,'-c',program],text=True))
            for name,h in hashes.items():
                source=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
                assert hashlib.sha256(source.replace(b'\r\n',b'\n')).hexdigest()==h,name
            result['sources'][image]=dict(commit=commit,sha256_lf_normalized=hashes)
    result['unused_repeats']=[]
    all_extension_cost=0
    for journal in sorted((OUT/'extensions').glob('*/harness/trajectory.jsonl')):
        es=events(journal);cost=round(sum(e['cost'] for e in es if e['event']=='llm_call'),1)
        all_extension_cost+=cost
        name=journal.parents[1].name
        if not name.endswith('-101'):
            result['unused_repeats'].append(dict(directory=name,charged_cost=cost,
                reason='Not included: user requested one run; structural-102 suffered host Windows memory error and its container was stopped.'))
    result['total_experiment_meter_weighted_tokens']=round(original['total_experiment_weighted_tokens']+all_extension_cost+result['runs'][-1]['spent'],1)
    result['limitations']=['One trial per variant, same seed101; no statistical significance claim.',
        'Later hypotheses on a previously inspected control set, not a fresh blind holdout.',
        'Training and hyperparameter selection use only the original 140 training attempts.',
        'Memory is sampled Docker stats; encoder_probe has peak RSS of a separate encoder process.',
        'A Windows host commit-memory failure interrupted an unused repeat, not a valid scored trial.']
    labels={'baseline':'Текущая очередь','numeric':'Признаки с ключевыми словами','embedding':'Признаки + MiniLM INT8',
        'structural':'Признаки без ключевых слов','strong_embedding':'Только BGE FP32','bge_structural':'BGE FP32 + признаки без ключевых слов'}
    lines=['# Один прогон каждого из шести вариантов','',
        '34 задачи, 119 возможных баллов, одинаковый seed101. Бюджет — 12000 взвешенных токенов; возможен перерасход одним вызовом. Старые варианты представлены первым прогоном, а не средним по трём.','',
        '| Вариант | Баллы | Верно | Расход | Время, с | Подготовка прогнозов, с |','|---|---|---|---|---|---|']
    for r in result['runs']:
        lines.append(f"| {labels[r['mode']]} | {r['points']:g} | {r['correct']} | {r['spent']:.1f} | {r['seconds']:.1f} | {r['prediction_init_seconds']:.2f} |")
    lines+=['','Модели обучены на тех же 140 попытках и 60 группах; новые LLM-прогоны для обучения не потребовались. У structural 18 входов: тип, длины, размеры и структура файлов без счётчиков слов в условии и коде. У strong_embedding только 768 чисел BGE; у bge_structural их конкатенация с 18 признаками, всего 786. Во всех вариантах reward используется при ранжировании, не как обучающий признак.','',
        'BGE-base-en-v1.5: неквантованный ONNX, CLS pooling, нормализация, до 512 токенов во фрагменте и 6 фрагментов. Источник и revision сохранены в predictors/encoder-strong/provenance.json. Бинарные веса исключены из Git, загружаются до сборки; во время конкурса сеть для энкодера не нужна.','',
        'Лимиты контейнеров: 8 CPU, memory16g, tmpfs2g, pids512, deadline3600 секунд. Образы меньше 4 ГБ; точные размеры и выборочная память — в results.json. Отдельная проверка энкодера: 34 условия за 6.35 с после загрузки 3.16 с; peak RSS около 827 МиБ. Обработка длинного примера ограничена числом фрагментов.','',
        'Во время дополнительного повтора на хосте Windows возник WinError1455 при запуске docker stats. Запуск не входит в таблицу; контейнер остановлен, повторы прекращены по пожеланию пользователя. Его расход сохранён отдельно. Мониторинг ресурсов теперь сохраняет ошибку опроса, не обрывая исправно работающий агент. Итоговый комбинированный прогон выполнялся отдельно от обучения и сборки.','',
        'Один прогон не доказывает устойчивость преимущества. Новые варианты выбраны после просмотра предыдущих результатов, а контрольные задачи уже известны команде. Это абляция на общем наборе, не независимая финальная оценка закрытого конкурса. Параметры предикторов подбирались только на обучающих группах.','',
        f"Общий счётчик обучения и всех выполненных измерений, включая лишние и прерванные повторы: {result['total_experiment_meter_weighted_tokens']:.1f}. В этот расход не входят локальные эмбеддинги: они не вызывают прокси.",'']
    destination=ROOT/'docs/results/offline-predictors-v2';dump(destination/'results.json',result)
    (destination/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps([dict(mode=r['mode'],points=r['points'],spent=r['spent']) for r in result['runs']],indent=2))


if __name__=='__main__':main()
