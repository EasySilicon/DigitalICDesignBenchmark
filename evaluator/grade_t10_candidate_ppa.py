#!/usr/bin/env python3
"""Compute candidate T10 scores from real three-seed PE measurements only.

Writes a new evaluator report, not the frozen reference or candidate RTL.
Missing/failed measurements are errors, never synthesized zero scores.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess

from t10_candidate_physical import REPO, TRIALS, artifact, sha, write_new_or_same, active_records
from ppa_aggregate import source_hash
from score_run import expected_ppa_parameters, ppa_provenance_valid, score_run

BACKEND=REPO/'evaluator/t10_backend/v1'


def check_artifacts(value):
    if isinstance(value,dict):
        if {'path','bytes','sha256'}<=value.keys():
            if artifact(Path(value['path']))!=value:raise ValueError('measured artifact changed: '+value['path'])
        for child in value.values():check_artifacts(child)
    elif isinstance(value,list):
        for child in value:check_artifacts(child)


def number(path,pattern):
    match=re.search(pattern,path.read_text())
    if not match:raise ValueError('missing physical measurement: '+str(path))
    value=float(match[1])
    if not math.isfinite(value):raise ValueError('nonfinite physical measurement')
    return value


def drc_count(report):
    if not report.strip():return 0
    matches=re.findall(r'(?m)^\s*violation type:',report)
    if not matches:raise ValueError('unrecognized native route DRC report')
    return len(matches)


def workload_parameters(model_dir,reference):
    """Derive the scoring contract from measured vector bytes, not the baseline."""
    directory=model_dir/'workload';manifest_path=directory/'manifest.json'
    manifest=json.loads(manifest_path.read_text())
    if sha(manifest_path)!=reference['workload_sha256'] or manifest['task_id']!='T10' or \
            manifest['seed']!=20260925 or manifest['case_count']!=200:
        raise ValueError('candidate workload manifest changed')
    for name,record in manifest['files'].items():
        path=directory/name
        if path.stat().st_size!=record['bytes'] or sha(path)!=record['sha256']:
            raise ValueError('candidate workload vector changed: '+name)
    digest=hashlib.sha256()
    for name in ('a','b','as','bs','mode','phase'):
        payload=(directory/f'{name}.mem').read_bytes()
        digest.update(name.encode());digest.update(len(payload).to_bytes(8,'big'));digest.update(payload)
    params=dict(seed=manifest['seed'],case_count=manifest['case_count'],vectors_sha256=digest.hexdigest())
    if params!=reference['workload_parameters']:raise ValueError('actual workload differs from the frozen contract')
    return params


def seed_record(model_dir,seed,orfs,reference,*,cached_only=False):
    directory=model_dir/f'seed{seed}'
    input_path,physical_path=active_records(directory)
    inputs=json.loads(input_path.read_text())
    completed=json.loads(physical_path.read_text())
    power_path=model_dir/f'activity_seed{seed}/power.json'
    power=json.loads(power_path.read_text())
    if completed['exit_code'] or completed['inputs_sha256']!=sha(input_path):
        raise ValueError('candidate physical completion is invalid')
    check_artifacts(completed['artifacts']);check_artifacts(power)
    if power['physical_inputs']!=completed['artifacts'] or power['source_sha256']!=inputs['source_sha256'] or \
            power['layout_seed']!=seed or power['measurement_scope']!='single_pe' or \
            power['numerical_oracle_passed'] is not True or power['protocol_and_latency_passed'] is not True or \
            power['matrix_blocks']!=200 or power['output_points_checked']!=51200 or \
            power['workload_manifest']['sha256']!=reference['workload_sha256'] or \
            min(power['activity_annotation_fraction'],power['sequential_activity_annotation_fraction'])<.95:
        raise ValueError('incomplete/mismatched full-DUT activity and physical power')
    odb=completed['artifacts']['6_final.odb'];result_dir=Path(odb['path']).parent
    out=directory/'scoring_verification';out.mkdir(exist_ok=True)
    libs=sorted(p for p in (REPO/'vendor/asap7/lib/NLDM').glob('asap7sc7p5t_*RVT_SS_nldm_*.lib*') if 'FAKE' not in p.name)
    if len(libs)!=5:raise ValueError('expected five WC timing libraries')
    verifier=BACKEND/'verify_extracted.tcl'
    binding=dict(physical_inputs=completed['artifacts'],libraries=[artifact(p) for p in libs],verifier=artifact(verifier))
    write_new_or_same(out/'inputs.json',json.dumps(binding,indent=2)+'\n')
    if not (out/'timing.json').exists():
        if cached_only:raise ValueError('native timing cache is incomplete; refusing to start EDA while publishing')
        env=os.environ|dict(T10_LIBRARY_LIST=' '.join(map(str,libs)),T10_INPUT_ODB=str(result_dir/'6_final.odb'),
            T10_INPUT_SDC=str(result_dir/'6_final.sdc'),T10_INPUT_SPEF=str(result_dir/'6_final.spef'),T10_VERIFY_OUTPUT=str(out))
        with (out/'verification.log').open('x') as log:
            subprocess.run(['openroad','-exit','-no_init',str(verifier)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        values={name:number(out/(name+'.rpt'),r'worst slack (?:max|min)\s+([-+\d.eE]+)') for name in ('setup','hold')}
        if (out/'constraint_coverage.rpt').stat().st_size:raise ValueError('unconstrained physical paths')
        timing=dict(values=values,inputs_sha256=sha(out/'inputs.json'),reports={p.name:artifact(p) for p in out.glob('*.rpt')})
        (out/'timing.json').write_text(json.dumps(timing,indent=2)+'\n')
    timing=json.loads((out/'timing.json').read_text());check_artifacts(timing['reports'])
    if timing['inputs_sha256']!=sha(out/'inputs.json'):raise ValueError('timing provenance changed')
    reports=orfs/'flow/reports/asap7'/inputs['pe_module']/inputs['variant']
    metrics_path=orfs/'flow/logs/asap7'/inputs['pe_module']/inputs['variant']/'6_report.json'
    area=json.loads(metrics_path.read_text())['finish__design__instance__area']
    if area<=0:raise ValueError('nonpositive complete PE area')
    raw_drc=reports/'5_route_drc.rpt'
    return dict(layout_seed=seed,measurement_scope='single_pe',area_um2=area,
        resource_policy=completed.get('resource_policy'),
        delay_ns=(1000-timing['values']['setup'])/1000,
        setup_worst_slack_ns=timing['values']['setup']/1000,hold_worst_slack_ns=timing['values']['hold']/1000,
        drc_violations=drc_count(raw_drc.read_text()),energy_per_op_pj=power['energy_j_per_block']*1e12,
        power_w=power['total_power_w'],average_power_mw=power['total_power_w']*1000,ops=200,
        annotation_fraction=power['activity_annotation_fraction'],timing_record=artifact(out/'timing.json'),
        route_drc_report=artifact(raw_drc),area_metrics=artifact(metrics_path),power_record=artifact(power_path))


def grade(model,work,trials,orfs,*,cached_only=False):
    model_dir=work/model
    reference=json.loads((REPO/'benchmark/ppa-baselines.json').read_text())['tasks']['T10']
    rows=[seed_record(model_dir,s,orfs,reference,cached_only=cached_only) for s in (11,29,47)]
    measurement=dict(task_id='T10',measurement_scope='single_pe',measurement_status='three_seed_single_pe',
        source_sha256=source_hash(model_dir/'submission'),workload_id=reference['workload_id'],
        workload_sha256=reference['workload_sha256'],workload_parameters=workload_parameters(model_dir,reference),
        parameter_set=expected_ppa_parameters('T10'),routed=True,per_seed=rows,
        **{key:statistics.median(r[key] for r in rows) for key in ('area_um2','delay_ns','energy_per_op_pj','average_power_mw')},
        setup_worst_slack_ns=min(r['setup_worst_slack_ns'] for r in rows),hold_worst_slack_ns=min(r['hold_worst_slack_ns'] for r in rows),
        drc_violations=max(r['drc_violations'] for r in rows),annotation_fraction=min(r['annotation_fraction'] for r in rows))
    if not ppa_provenance_valid('T10',measurement,reference):raise ValueError('invalid candidate measurement provenance')
    original=trials/TRIALS[model]
    if source_hash(original/'workspaces/T10')!=measurement['source_sha256']:raise ValueError('original candidate source changed')
    public=json.loads((REPO/f'results/{model}/T10.json').read_text())
    functional=json.loads((original/'grading/T10/functional.json').read_text())
    # Astra's original structural checker did not support retained wrappers;
    # its published, corrected groups are bound to the same candidate hash.
    groups=public.get('functional_groups',functional['groups'])
    if public.get('functional_total')!=50:raise ValueError('candidate not functionally qualified')
    structure=json.loads((model_dir/'structure.json').read_text())
    if not structure['passed'] or structure['candidate_source_sha256']!=measurement['source_sha256']:
        raise ValueError('candidate structure not qualified')
    if functional.get('stream_line')!='MM_STREAM input_bubble_phases=00000000000000 finished=2752':
        raise ValueError('missing full continuous-stream acceptance')
    ws=original/'workspaces/T10'
    elapsed=float((ws/'trial_finished_epoch.txt').read_text())-float((ws/'trial_started_epoch.txt').read_text())
    delivery=json.loads((original/'grading/T10/delivery.json').read_text())
    payload=dict(task_id='T10',groups=groups,delivery_qualified=delivery['delivery_qualified'],elapsed_seconds=elapsed,
        time_limit_seconds=14400,sustained_throughput_passed=True,ppa_reference=reference,ppa_measurement=measurement,
        candidate_delivery_error_count=public.get('candidate_delivery_error_count',0))
    scored=score_run(payload)
    if not scored['ppa_eligible']:raise ValueError('measured record was rejected by the official scorer')
    return dict(model=model,measurement=measurement,score=scored,elapsed_seconds=elapsed,
        grading_resource_policy=rows[0].get('resource_policy'),
        original_functional_record=artifact(original/'grading/T10/functional.json'),structure=artifact(model_dir/'structure.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--trials-root',type=Path,required=True)
    p.add_argument('--orfs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('output exists; do not overwrite an audited report')
    reports=[grade(m,a.work.resolve(),a.trials_root.resolve(),a.orfs.resolve()) for m in TRIALS]
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(reports,indent=2)+'\n')
    for report in reports:print(report['model'],report['score']['ppa_score'])
