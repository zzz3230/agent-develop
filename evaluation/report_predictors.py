"""Publish compact reproducible experiment evidence, including resource and usage audits."""
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import os

from evaluation.predictor_experiment import ROOT,OUT,dump
from evaluation.audit_usage import audit


def memory_bytes(text):
    m=re.match(r'([\d.]+)([KMGT]?i?B)',text.strip())
    units={'B':1,'kB':1000,'KB':1000,'MB':1000**2,'GB':1000**3,
           'KiB':1024,'MiB':1024**2,'GiB':1024**3,'TiB':1024**4}
    return int(float(m[1])*units[m[2]]) if m else None


def main():
    comparisons=json.loads((OUT/'comparison.json').read_text(encoding='utf-8'))
    if len(comparisons)!=9: raise ValueError('Nine completed comparisons required')
    result=dict(protocol='140 charged graded training attempts; 34 held-out tasks; 3 repeats; 12000 offline cap',
                training=json.loads((OUT/'training_report.json').read_text(encoding='utf-8')),runs=[])
    agent_commit=subprocess.check_output(['git','log','-1','--format=%H','--','predictors/numeric.json'],cwd=ROOT,text=True).strip()
    fingerprint_code="import hashlib,json;from pathlib import Path;r=Path('/app');fs=[r/'run_agent.py',*sorted((r/'runtime').glob('*.py')),*sorted((r/'predictors').glob('*.json'))];print(json.dumps({p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest() for p in fs}))"
    fingerprints=json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--entrypoint','python',
        'agent-develop:predictors','-c',fingerprint_code],text=True))
    for name,value in fingerprints.items():
        content=subprocess.check_output(['git','show',agent_commit+':'+name],cwd=ROOT)
        assert hashlib.sha256(content.replace(b'\r\n',b'\n')).hexdigest()==value, 'Image source mismatch: '+name
    result['agent_source_commit']=agent_commit
    result['agent_source_sha256_lf_normalized']=fingerprints
    result['grader_driver_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    for r in comparisons:
        directory=OUT/f"{r['mode']}-{r['seed']}"
        info=json.loads((directory/'run.json').read_text(encoding='utf-8'))
        grade=json.loads((directory/'graded.json').read_text(encoding='utf-8'))
        events=[json.loads(s) for s in (directory/'harness/trajectory.jsonl').read_text(encoding='utf-8').splitlines()]
        calls=[e for e in events if e['event']=='llm_call']
        usage_audit=audit(directory/'console.log')
        mem=[memory_bytes(s['MemUsage'].split('/')[0]) for s in info['resource_samples']]
        mem=[v for v in mem if v is not None]
        row={k:v for k,v in r.items() if k!='run'}
        row.update(image_id=info['image_id'],agent_commit=agent_commit,driver_commit=info['commit'],points_possible=grade['total']['possible'],
            sampled_peak_memory_bytes=max(mem,default=0),sampled_peak_cpu_percent=max([float(s['CPUPerc'].strip('%')) for s in info['resource_samples']],default=0),
            sampled_peak_pids=max([int(s['PIDs']) for s in info['resource_samples']],default=0),
            prediction_init_seconds=next((e['seconds'] for e in events if e['event']=='predictor_init'),0),
            calls=len(calls),estimated_calls=sum(bool(e.get('estimated')) for e in calls),
            input_tokens=sum(e['input'] for e in calls),output_tokens=sum(e['output'] for e in calls),
            budget_overrun=round(r['spent']-12000,1),stopped_by=info['stopped_by'],
            api_retries=sum(e['event']=='llm_retry' for e in events),usage_audit=usage_audit,
            incorrect=[dict(id=x['id'],note=x['note']) for x in grade['rows'] if x['solvable'] and not x['correct'] and x['journal_status']!='not_run'])
        row['proxy_reported_weighted_tokens']=round(r['spent']-usage_audit['extra_cost'],1) if len(calls)==usage_audit['responses'] and not row['estimated_calls'] else None
        assert r['seconds']<3600 and row['sampled_peak_memory_bytes']<16*1024**3
        result['runs'].append(row)
    images=json.loads(subprocess.check_output(['docker','image','inspect','agent-develop:predictors','agent-develop:predictor-source-base'],text=True))
    result['images']=[dict(id=i['Id'],tags=i['RepoTags'],bytes=i['Size']) for i in images]
    build_log=OUT/'source-build.log'
    result['source_build_wall_seconds_from_log_timestamps']=round(build_log.stat().st_mtime-build_log.stat().st_ctime,1) if build_log.exists() and os.name=='nt' else None
    if result['source_build_wall_seconds_from_log_timestamps'] is not None:
        assert result['source_build_wall_seconds_from_log_timestamps']<1000
    assert all(i['Size']<4_000_000_000 for i in images)
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0')
    result['tracked_source_bytes']=sum((ROOT/p).stat().st_size for p in tracked if p and (ROOT/p).is_file())
    assert result['tracked_source_bytes']<100_000_000
    h=hashlib.sha256()
    for p in sorted((OUT/'control/input').rglob('*')):
        if p.is_file():h.update(p.relative_to(OUT/'control/input').as_posix().encode()+b'\0'+p.read_bytes())
    result['control_input_sha256']=h.hexdigest()
    result['models_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'predictors').glob('*.json')}
    training_cost=sum(json.loads((OUT/n/'graded.json').read_text(encoding='utf-8'))['spent'] for n in ('train-old','train-dev'))
    result['total_experiment_weighted_tokens']=round(training_cost+sum(r['spent'] for r in comparisons),1)
    result['training_usage_audits']={n:audit(OUT/n/'console.log') for n in ('train-old','train-dev')}
    result['total_character_floor_overestimate']=sum(r['usage_audit']['extra_cost'] for r in result['runs'])+sum(a['extra_cost'] for a in result['training_usage_audits'].values())
    result['summary']={}
    lines=['# Сравнение предварительно обученных планировщиков','',
        '34 контрольные задачи, 119 возможных баллов, три повтора. Бюджет каждого прогона — 12000 взвешенных токенов, с возможным превышением одним вызовом. Все ответы повторно оценены общим проверяющим; код без DONE в answer.txt не засчитывается.','',
        '| Вариант | Баллы по повторам | Средние баллы | Средний расход | Среднее время, с |',
        '|---|---|---|---|---|']
    for mode in ('baseline','numeric','embedding'):
        selected=[r for r in result['runs'] if r['mode']==mode]
        summary={k:dict(mean=statistics.mean(r[k] for r in selected),min=min(r[k] for r in selected),max=max(r[k] for r in selected))
                 for k in ('points','correct','spent','seconds','sampled_peak_memory_bytes','prediction_init_seconds')}
        result['summary'][mode]=summary
        lines.append(f"| {mode} | {', '.join(str(r['points']) for r in selected)} | {summary['points']['mean']:.1f} | {summary['spent']['mean']:.1f} | {summary['seconds']['mean']:.1f} |")
    lines+=['',f"Обучение и девять контрольных прогонов суммарно потребовали {result['total_experiment_weighted_tokens']:.1f} взвешенного токена. Это сумма нескольких запусков, не расход одного конкурсного запуска.",'',
        'Метрики подбора и точные параметры находятся в results.json. Память и CPU в таблице JSON — выборочные максимумы Docker stats, не непрерывное измерение пиков. Образ общий для трёх вариантов; baseline не загружает энкодер. Измерение бюджетного порядка на этом наборе не предсказывает качество на более трудной закрытой выборке.','',
        'Данные контрольной выборки не использовались в подборе коэффициентов. Метрики GroupKFold использовались для выбора регуляризации и не считаются независимой итоговой оценкой. Три повтора показывают разброс, но не доказывают статистическую значимость.','',
        'Первый baseline-прогон частично совпал по времени с завершением сборки отдельного образа. Остальные контрольные прогоны выполнялись без сборки. Это ограничивает сравнение времени первого прогона; все запуски имели одинаковые явные ограничения CPU и памяти.','']
    destination=ROOT/'docs/results/offline-predictors-v1';destination.mkdir(parents=True,exist_ok=True)
    dump(destination/'results.json',result)
    (destination/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
