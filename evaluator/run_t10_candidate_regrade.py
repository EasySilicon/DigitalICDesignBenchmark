#!/usr/bin/env python3
"""Follow one identified physical queue, measure power, then score real records.

Produces host-side calculation reports only; does not publish, commit or push.
Infrastructure failures and missing seeds remain pending, not invented zeros.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import time
import traceback

from t10_candidate_physical import REPO, TRIALS, sha
from grade_t10_candidate_ppa import grade
from ppa_aggregate import source_hash
from power_compile_budget import TIMEOUT_EXIT_CODE, TIMEOUT_STATUS, validate_timeout
from t10_candidate_physical import artifact


def save(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');temporary.replace(path)


def run_power(command, root, seed):
    """Exit 124 alone is insufficient: require this source/seed's receipt."""
    with (root/f'seed{seed}/activity_queue.log').open('x') as log:
        result=subprocess.run(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode == TIMEOUT_EXIT_CODE:
        path=root/f'activity_seed{seed}/power_compile.json'
        validate_timeout(json.loads(path.read_text()),source_hash(root/'submission'),seed)
        return dict(status=TIMEOUT_STATUS,ppa_score=0,time_score=0,
                    failing_seed=seed,evidence=artifact(path))
    result.check_returncode()
    return None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--physical-supervisor-pid',type=int,required=True)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--trials-root',type=Path,required=True)
    p.add_argument('--orfs',type=Path,required=True)
    a=p.parse_args();work=a.work.resolve();work.mkdir(exist_ok=True,parents=True)
    proc=Path(f'/proc/{a.physical_supervisor_pid}/stat')
    identity=proc.read_text().split()[21] if proc.exists() else None
    status=dict(status='waiting_for_identified_physical_queue',physical_supervisor_pid=a.physical_supervisor_pid,
        process_start_ticks=identity,runner_sha256=sha(Path(__file__)),models={})
    for model in ('kimi-k3','deepseek-flash','glm-5.3-flash'):
        row=json.loads((REPO/f'results/{model}/T10.json').read_text())
        if row.get('ppa_score')!=0 or row.get('full_functional_pass') is True:
            raise ValueError('existing zero requires independent review: '+model)
        status['models'][model]=dict(status='existing_functional_or_delivery_gate_zero',ppa_score=0)
    for model in TRIALS:status['models'][model]=dict(status='physical_pending',ppa_score=None)
    output=work/'t10_ppa_scores.json'
    if output.exists():raise ValueError('regrade state already exists; inspect existing queue instead of restarting')
    save(output,status)
    print('FOLLOW PHYSICAL SUPERVISOR',a.physical_supervisor_pid,flush=True)
    while identity is not None:
        try:
            if proc.read_text().split()[21]!=identity:break
        except FileNotFoundError:break
        time.sleep(10)
    for model in TRIALS:
        record=status['models'][model];record['status']='checking_physical_outputs'
        status.update(status='measuring_completed_candidates',updated_utc=dt.datetime.now(dt.timezone.utc).isoformat());save(output,status)
        try:
            root=work/model
            for seed in (11,29,47):
                physical=json.loads((root/f'seed{seed}/baseline.json').read_text())
                if physical['exit_code']!=0:raise ValueError(f'seed {seed}: physical failure needs attribution')
            for seed in (11,29,47):
                record.update(status='activity_and_power_running',layout_seed=seed);save(output,status)
                print('ACTIVITY/POWER',model,seed,flush=True)
                command=['systemd-run','--user','--scope',
                    f'--unit=t10-power-{model.replace(".","_")}-s{seed}',
                    '-p','MemoryMax=40G','-p','MemorySwapMax=0','-p','CPUQuota=400%',
                    'python3','-u',str(REPO/'evaluator/t10_candidate_power.py'),
                    '--model-dir',str(root),'--seed',str(seed),'--orfs',str(a.orfs.resolve())]
                timeout=run_power(command,root,seed)
                if timeout:
                    record.update(timeout)
                    break
            if record['ppa_score']==0:
                save(output,status)
                continue
            report=grade(model,work,a.trials_root.resolve(),a.orfs.resolve())
            report_path=root/'scored.json'
            if report_path.exists():raise ValueError('scored report already exists')
            report_path.write_text(json.dumps(report,indent=2)+'\n')
            record.update(status='measured_and_scored',ppa_score=report['score']['ppa_score'],
                time_score=report['score']['time_score'],display_score=report['score']['display_score'],
                report_path=str(report_path),report_sha256=sha(report_path))
        except Exception:
            record.update(status='pending_failure_attribution',ppa_score=None,diagnostic=traceback.format_exc())
            print('PENDING ATTRIBUTION',model,record['diagnostic'],flush=True)
        save(output,status)
    complete=all(r['ppa_score'] is not None for r in status['models'].values())
    status.update(status='all_six_scores_available' if complete else 'partial_scores_pending_attribution',
        updated_utc=dt.datetime.now(dt.timezone.utc).isoformat());save(output,status)
    print(status['status'],output,flush=True)


if __name__=='__main__':main()
