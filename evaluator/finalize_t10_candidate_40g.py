#!/usr/bin/env python3
"""After the serial measurement queue exits, verify and finalize cached scores.

Waits on the same exclusive lock; never runs measurement jobs in parallel or
repeats completed power/physical flows. Missing evidence remains unscored.
"""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import shutil
import traceback

from grade_t10_candidate_ppa import grade
from run_t10_candidate_40g import POLICY,assert_serial,save
from t10_candidate_physical import TRIALS,artifact,sha,write_new_or_same


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('work','trials-root','orfs'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--controller-unit',required=True)
    args=parser.parse_args();work=args.work.resolve()
    with (work/'serial40.lock').open('a') as lock:
        print('WAITING for the measurement coordinator lock; no EDA work started',flush=True)
        fcntl.flock(lock,fcntl.LOCK_EX)
        assert_serial()
        path=work/'t10_ppa_scores40.json';state=json.loads(path.read_text())
        if state['policy']!=POLICY:raise ValueError('resource policy changed')
        backup=work/'scores40_before_workload_metadata_repair.json'
        if not backup.exists():shutil.copy2(path,backup)
        state.update(status='finalizing_scoring_metadata',controller_unit=args.controller_unit,
            finalizer_sha256=sha(Path(__file__)),
            finalization_started_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        save(path,state)
        for model in ('gpt-6.1-sol','gpt-6-astra','gpt-6-sol'):
            row=state['models'][model]
            if row['ppa_score'] is not None:continue
            try:
                # Refuse to manufacture a score or restart a missing measurement.
                for seed in (11,29,47):
                    if not (work/model/f'activity_seed{seed}/power.json').exists():
                        raise ValueError(f'{model} seed {seed}: power measurement not complete')
                report=grade(model,work,args.trials_root.resolve(),args.orfs.resolve())
                output=work/model/'scored40.json'
                write_new_or_same(output,json.dumps(report,indent=2)+'\n')
                if 'diagnostic' in row:row['previous_aggregation_diagnostic']=row.pop('diagnostic')
                row.update(status='measured_and_scored_40g',ppa_score=report['score']['ppa_score'],
                    time_score=report['score']['time_score'],display_score=report['score']['display_score'],
                    report=artifact(output))
                print('SCORED',model,row['ppa_score'],flush=True)
            except Exception:
                row.update(status='pending_infrastructure_review',diagnostic=traceback.format_exc())
                print('PENDING',model,row['diagnostic'],flush=True)
            save(path,state)
        state['status']='complete' if all(row['ppa_score'] is not None for row in state['models'].values()) else 'pending_infrastructure_review'
        save(path,state)


if __name__=='__main__':main()
