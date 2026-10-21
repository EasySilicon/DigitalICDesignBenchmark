#!/usr/bin/env python3
"""Publish only verified T10 scores; preserve other tasks and trial evidence."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shutil

from t10_candidate_physical import REPO, TRIALS, artifact, prepare
from grade_t10_candidate_ppa import grade
from run_t10_candidate_40g import POLICY, save
from score_run import load_rules, score_run, weighted_suite_score
from adjudicate_t10_compile_stop import STATUS as COMPILE_STOP_ZERO, validate_decision

SCORING_POLICY='functional50-ppa50-setup-frequency-power4-hold-continuous-drc-half-delivery-v6'


def verified_report(model,state,work,trials,orfs,*,allow_cached=False):
    row=state['models'][model]
    if row['ppa_score'] is None:
        if not allow_cached:raise ValueError('T10 measurement is incomplete: '+model)
        # The live coordinator owns the queue state. Independently verified
        # reports may be published without editing its in-memory state or
        # waiting for another candidate's measurements to finish.
        path=work/model/'scored40.json'
        saved=json.loads(path.read_text())
        prepare(model,trials,work)
        regenerated=grade(model,work,trials,orfs,cached_only=True)
        if saved!=regenerated or saved.get('model')!=model:
            raise ValueError('cached report disagrees with verified native measurements')
        return saved
    item=prepare(model,trials,work)
    if row['status']=='measured_and_scored_40g':
        evidence=row['report'];path=Path(evidence['path'])
        if artifact(path)!=evidence:raise ValueError('scored report changed')
        saved=json.loads(path.read_text())
        regenerated=grade(model,work,trials,orfs,cached_only=True)
        if saved!=regenerated or saved['score']['ppa_score']!=row['ppa_score']:
            raise ValueError('official rescoring disagrees with completed measurement')
        return saved
    allowed={'user_adjudicated_40g_oom_zero','user_adjudicated_40g_power_oom_zero',COMPILE_STOP_ZERO}
    if row['status'] not in allowed or row['ppa_score']!=0:
        raise ValueError('unadjudicated failure cannot become a zero score')
    seed=row['failing_seed'];directory=work/model/f'seed{seed}'
    name='activity_runtime40.json' if row['status'].endswith('power_oom_zero') or row['status']==COMPILE_STOP_ZERO else 'runtime40.json'
    runtime_path=directory/name;runtime=json.loads(runtime_path.read_text())
    decision=None
    if row['status']==COMPILE_STOP_ZERO:
        evidence=row['adjudication'];path=Path(evidence['path'])
        if artifact(path)!=evidence:raise ValueError('user stop decision changed')
        decision=json.loads(path.read_text())
        validate_decision(decision,runtime,model,item['source_sha256'])
        for binding in (decision['request'],decision['terminal_runtime'],decision['queue_after_stop'],*decision['preserved_inputs'].values()):
            if artifact(Path(binding['path']))!=binding:raise ValueError('user stop evidence changed')
        if decision['terminal_runtime']!=artifact(runtime_path):raise ValueError('stopped runtime changed')
    elif runtime.get('confirmed') is not True or runtime.get('systemd_result')!='oom-kill' or runtime['policy']!=POLICY:
        raise ValueError('missing confirmed OOM under the authorized resource policy')
    inputs=json.loads((directory/'inputs40.json').read_text())
    if inputs['source_sha256']!=item['source_sha256']:raise ValueError('OOM candidate source changed')
    original=json.loads((REPO/f'results/{model}/T10.json').read_text())
    trial=trials/TRIALS[model];workspace=trial/'workspaces/T10'
    functional_path=trial/'grading/T10/functional.json'
    functional=json.loads(functional_path.read_text())
    delivery=json.loads((trial/'grading/T10/delivery.json').read_text())
    elapsed=float((workspace/'trial_finished_epoch.txt').read_text())-float((workspace/'trial_started_epoch.txt').read_text())
    payload=dict(task_id='T10',groups=original.get('functional_groups',functional['groups']),delivery_qualified=delivery['delivery_qualified'],
        elapsed_seconds=elapsed,time_limit_seconds=original['time_limit_seconds'],
        sustained_throughput_passed=True,candidate_delivery_error_count=original.get('candidate_delivery_error_count',0))
    scored=score_run(payload)
    if scored['functional_total']!=50 or scored['ppa_score']!=0:raise ValueError('unexpected resource-zero score')
    return dict(model=model,score=scored,elapsed_seconds=elapsed,
        original_functional_record=artifact(functional_path),
        candidate_source_sha256=item['source_sha256'],grading_resource_policy=POLICY,
        adjudication=decision['reason'] if decision else 'user-authorized PPA zero after confirmed 40 GiB OOM, swap allowed',
        user_decision=row['adjudication'] if decision else None,
        user_decision_record=decision,
        measurement_completed=False,failing_seed=seed,runtime=artifact(runtime_path),queue_status=row['status'])


def task_record(old,report,receipt,stamp,*,verified_source=None):
    source=report.get('candidate_source_sha256',report.get('measurement',{}).get('source_sha256'))
    previous_source=old.get('candidate_sha256')
    if not source or (previous_source is None and verified_source!=source) or \
            (previous_source is not None and previous_source!=source) or \
            old['functional_total']!=report['score']['functional_total']:
        raise ValueError('publication would change candidate identity or functional result')
    updated=copy.deepcopy(old)
    updated.update(report['score'])
    updated.update(score_status='scored',result_revision_date=stamp,scoring_policy=SCORING_POLICY,
        elapsed_seconds=report['elapsed_seconds'],candidate_sha256=source,
        ppa_possible=50,time_possible=5,display_possible=105,ranking_eligible=False,
        ranking_ineligible_reason='Historical pilot; common tool-image and suite release qualification remain pending.',
        t10_ppa_remeasurement=dict(report=receipt,resource_policy=POLICY,
            note='User-authorized serial 40 GiB remeasurement with swap; not 32 GiB compliance.'))
    if 'measurement' in report:updated['ppa_measurement']=report['measurement']
    elif report.get('queue_status')==COMPILE_STOP_ZERO:
        updated['ppa_adjudication']=report['adjudication']
        updated['scoring_policy']=SCORING_POLICY+'+explicit-user-compile-stop-zero'
    else:updated['resource_failure_adjudication']=report['adjudication']
    if 'functional_groups' not in updated and 'original_functional_record' in report:
        evidence=report['original_functional_record'];path=Path(evidence['path'])
        if artifact(path)!=evidence:raise ValueError('original functional record changed')
        updated['functional_groups']=json.loads(path.read_text())['groups']
    return updated


def summary_record(old,updated,stamp):
    result=copy.deepcopy(old)
    fields={key:updated[key] for key in (
        'functional_total','full_functional_pass','delivery_qualified','candidate_sha256',
        'ppa_eligible','ppa_score','ppa_rank_bucket','time_score',
        'display_score','candidate_delivery_error_count','candidate_delivery_penalty',
        'display_score_before_candidate_penalty','score_status','scoring_policy','elapsed_seconds','t10_ppa_remeasurement')}
    rows=result['tasks']
    if sum(row['task_id']=='T10' for row in rows)!=1:raise ValueError('summary must contain exactly one T10')
    for row in rows:
        if row['task_id']=='T10':row.update(fields)
    # Historical summaries have mixed suite revisions. Bind this remeasurement
    # explicitly without relabelling the policy used by any other task.
    result.setdefault('task_scoring_policies',{})['T10']=updated['scoring_policy']
    totals={key:math.fsum(row[key] for row in rows if row.get(key) is not None)
        for key in ('functional_total','ppa_score','time_score','display_score')}
    for key,names in {
        'functional_total':('functional_score_sum','functional_total_sum'),
        'ppa_score':('ppa_score_sum_for_available_tasks','ppa_score_sum'),
        'time_score':('time_score_sum_for_available_tasks','time_score_sum'),
        'display_score':('display_score_subtotal_with_unscored_components_omitted','display_score_sum')}.items():
        for name in names:result[name]=totals[key]
    weighted=weighted_suite_score({row['task_id']:row.get('display_score') for row in rows})
    result.update(weighted)
    result.update(weighted_display_score_with_unscored_components_omitted=weighted['weighted_display_score'],
        weighted_display_score_possible=weighted['weighted_display_possible'],
        weighted_task_contributions=weighted['weighted_contributions'],task_weights=load_rules()['task_weights'])
    pending={row['task_id']:[key for key in ('functional_total','ppa_score','time_score') if row.get(key) is None]
        for row in rows if any(row.get(key) is None for key in ('functional_total','ppa_score','time_score'))}
    result.update(pending_components=pending,totals_complete=not pending,
        complete_display_score_task_count=len(rows)-len(pending),result_revision_date=stamp,ranking_eligible=False,
        ranking_ineligible_reasons=[
            'Historical pilots; common tool-image and suite release qualification remain pending.',
            'T10 used the user-authorized serial 40 GiB policy with swap, not the default 32 GiB policy.',
            'T10 reference uses custom internal hard macros; historical candidates use flat PE implementations.'])
    if 'remaining_unscored_component' in result:result['remaining_unscored_component']=pending
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('work','trials-root','orfs'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--models',nargs='+',choices=TRIALS,default=list(TRIALS))
    parser.add_argument('--allow-partial',action='store_true',
        help='publish only selected, independently reverified cached reports; never score missing measurements')
    args=parser.parse_args();work=args.work.resolve()
    state=json.loads((work/'t10_ppa_scores40.json').read_text())
    if state['policy']!=POLICY:raise ValueError('resource policy changed')
    if state['status']!='complete' and not args.allow_partial:raise ValueError('entire score queue must be complete')
    reports={model:verified_report(model,state,work,args.trials_root.resolve(),args.orfs.resolve(),
        allow_cached=args.allow_partial) for model in args.models}
    stamp=dt.datetime.now().astimezone().date().isoformat();prepared=[]
    for model,report in reports.items():
        directory=REPO/'results'/model;receipt_path=directory/'T10-ppa40.json'
        # Bind the archived copy, not the scratch report's former location.
        encoded=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode()
        receipt=dict(path=str(receipt_path.relative_to(REPO)),bytes=len(encoded),sha256=hashlib.sha256(encoded).hexdigest())
        source=report.get('candidate_source_sha256',report.get('measurement',{}).get('source_sha256'))
        task=task_record(json.loads((directory/'T10.json').read_text()),report,receipt,stamp,verified_source=source)
        summary=summary_record(json.loads((directory/'summary.json').read_text()),task,stamp)
        prepared.append((model,directory,report,task,summary))
    if args.write:
        for model,directory,report,task,summary in prepared:
            backup=work/'publication_backup40'/model;backup.mkdir(parents=True,exist_ok=True)
            for name in ('T10.json','summary.json'):
                if not (backup/name).exists():shutil.copy2(directory/name,backup/name)
            save(directory/'T10-ppa40.json',report);save(directory/'T10.json',task);save(directory/'summary.json',summary)
    for model,_,_,task,summary in prepared:
        print(model,task['ppa_score'],task['time_score'],task['display_score'],
            summary['weighted_display_score_with_unscored_components_omitted'])


if __name__=='__main__':main()
