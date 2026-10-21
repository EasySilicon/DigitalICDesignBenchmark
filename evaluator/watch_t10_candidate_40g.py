#!/usr/bin/env python3
"""Small read-only EDA watchdog, invoked periodically by a user systemd timer.

Writes monitoring records and optional desktop notifications only. Never starts,
retries, stops, or scores candidate EDA jobs. Does not invoke a language model.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import time

from run_t10_candidate_40g import POLICY, properties, sample, save


def active_scopes():
    output=subprocess.check_output(['systemctl','--user','list-units','--state=active',
        '--type=scope','--plain','--no-legend','--no-pager'],text=True)
    names=[line.split()[0] for line in output.splitlines() if line.strip()]
    return [name for name in names if name.startswith(('ic_t10_candidate_','t10-power-','t10-40-power-'))]


def inspect(work,orfs,controller):
    state=json.loads((work/'t10_ppa_scores40.json').read_text())
    report=dict(checked_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        queue_status=state['status'],models=state['models'],alerts=[],active_scopes=[],progress=[])
    if state['policy']!=POLICY:report['alerts'].append('评分队列的资源设置发生变化')
    scopes=active_scopes()
    if len(scopes)>1:report['alerts'].append('发现多个候选模型任务并行运行')
    for unit in scopes:
        props=properties(unit)
        row=dict(unit=unit,properties=props)
        try:
            values=sample(props['ControlGroup'])
            row.update(resources=values,ram_gib=int(values['memory.current'])/1024**3,
                peak_ram_gib=int(values['memory.peak'])/1024**3,
                swap_gib=int(values['memory.swap.current'])/1024**3)
        except (KeyError,FileNotFoundError):row['note']='任务正在切换，下一轮重新检查'
        except ValueError as error:report['alerts'].append(str(error))
        report['active_scopes'].append(row)
    controller=state.get('controller_unit',controller)
    if not controller.startswith('ic-bcmk-t10-serial40-controller-'):
        raise ValueError('unexpected controller unit')
    report['controller_unit']=controller
    report['controller']=properties(controller) if controller.endswith('.scope') else service_properties(controller)
    terminal=state['status'] in ('complete','pending_infrastructure_review')
    if report['controller'].get('ActiveState')!='active' and not terminal:
        report['alerts'].append('串行调度进程已退出，但评分队列尚未结束')
    for model,row in state['models'].items():
        if row['status']=='pending_infrastructure_review':report['alerts'].append(model+' 需要排查基础设施错误')
        if row['status'] not in ('physical_running','activity_power_running'):continue
        directory=work/model/f'seed{row["layout_seed"]}'
        entry=dict(model=model,seed=row['layout_seed'],phase=row['status'])
        logs=[]
        if row['status']=='physical_running' and (directory/'inputs40.json').exists():
            inputs=json.loads((directory/'inputs40.json').read_text())
            logdir=orfs/'flow/logs/asap7'/inputs['pe_module']/inputs['variant']
            if logdir.exists():logs=list(logdir.glob('*.log'))
        elif (directory/'activity40.log').exists():logs=[directory/'activity40.log']
        if logs:
            latest=max(logs,key=lambda path:path.stat().st_mtime)
            entry.update(log=str(latest),log_age_seconds=round(time.time()-latest.stat().st_mtime))
            if entry['log_age_seconds']>7200:
                report['alerts'].append(f'{model} seed {row["layout_seed"]} 日志两小时未更新，需要检查（不自动重跑）')
        report['progress'].append(entry)
    report['terminal']=terminal and report['controller'].get('ActiveState')!='active' and not scopes
    return report


def service_properties(unit):
    if not unit.endswith('.service'):raise ValueError('explicit service suffix required')
    result=subprocess.run(['systemctl','--user','show',unit,'-p','ActiveState','-p','Result'],
        text=True,capture_output=True,check=False)
    return dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)


def event_key(report):
    return [report['queue_status'],report['alerts'],
        sorted((model,row['status'],row.get('layout_seed'),row.get('ppa_score'))
            for model,row in report['models'].items())]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--orfs',type=Path,required=True)
    parser.add_argument('--controller',required=True)
    parser.add_argument('--timer-unit')
    parser.add_argument('--notify',action='store_true')
    args=parser.parse_args()
    path=args.work/'monitor40.json'
    previous=json.loads(path.read_text()) if path.exists() else None
    report=inspect(args.work,args.orfs,args.controller)
    changed=previous is None or event_key(previous)!=event_key(report)
    if changed:
        with (args.work/'monitor40_events.jsonl').open('a') as stream:
            stream.write(json.dumps(report,ensure_ascii=False)+'\n')
        if args.notify and shutil.which('notify-send'):
            messages=report['alerts'] or [f'{p["model"]} seed {p["seed"]}：'+
                ('物理实现中' if p['phase']=='physical_running' else '活动功耗测量中') for p in report['progress']]
            if report['terminal']:messages.append('本轮评分队列已结束：'+report['queue_status'])
            try:
                result=subprocess.run(['notify-send','--app-name=T10 PPA 巡检',
                    'T10 评分进度', '\n'.join(messages) or report['queue_status']],timeout=10,check=False)
                report['notification_exit_code']=result.returncode
            except subprocess.TimeoutExpired:report['notification_error']='desktop notification timed out'
    save(path,report)
    print(json.dumps(report,ensure_ascii=False))
    if report['terminal'] and args.timer_unit:
        if not args.timer_unit.startswith('ic-bcmk-t10-watch-') or not args.timer_unit.endswith('.timer'):
            raise ValueError('refusing to stop an unrelated timer')
        subprocess.run(['systemctl','--user','stop',args.timer_unit],check=True)


if __name__=='__main__':main()
