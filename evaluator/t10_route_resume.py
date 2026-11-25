"""Resume a source-bound PE global-route checkpoint in a new attempt.

Only router concurrency changes. Original artifacts are preserved, and prior
active implementation time remains charged against the 7,200-second limit.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

from t10_candidate_physical import active_records, run_seed
from t10_hybrid_ppa import artifact, check, source_hash, write
from run_t10_candidate_40g import POLICY, assert_serial, monitor
from physical_budget import limit_seconds


def plan(item, seed, work, orfs, previous, *, threads=1, pause_record=None):
    previous = Path(previous)
    ip, pp = active_records(previous / f'seed{seed}')
    old = json.loads(ip.read_text())
    failed = json.loads(pp.read_text())
    budget_path = previous / f'seed{seed}/physical_budget.json'
    budget = json.loads(budget_path.read_text())
    elapsed = budget['elapsed_seconds']
    if (old['source_sha256'] != item['source_sha256'] or old['pe_module'] != item['pe']
            or old['layout_seed'] != seed or failed['inputs_sha256'] != artifact(ip)['sha256']
            or budget['candidate_source_sha256'] != item['source_sha256']
            or budget['layout_seed'] != seed or budget['task_id'] != 'T10'
            or budget['limit_seconds'] != limit_seconds('T10')
            or not 0 <= elapsed < limit_seconds('T10')
            or source_hash(previous / 'submission') != item['source_sha256']
            or source_hash(item['submission']) != item['source_sha256']):
        raise ValueError('resume source, seed, checkpoint or accumulated budget differs')
    check(failed['runtime'])
    runtime = json.loads(Path(failed['runtime']['path']).read_text())
    if (runtime.get('confirmed') is not True or runtime.get('systemd_result') != 'oom-kill'
            or runtime.get('policy') != POLICY):
        raise ValueError('explicit OOM checkpoint recovery requires confirmed resource evidence')
    pause_evidence = None
    if pause_record is not None:
        paused = json.loads(Path(pause_record).read_text())
        saved_path = Path(paused['preserved_resume_plan'])
        saved = json.loads(saved_path.read_text())
        extra = paused['retry_active_seconds']
        if (paused.get('status') != 'paused_by_user' or paused.get('current_seed') != seed
                or saved['inputs']['source_sha256'] != item['source_sha256']
                or saved['inputs']['layout_seed'] != seed
                or saved['inputs']['checkpoint_resume']['original_inputs'] != artifact(ip)
                or paused['prior_active_seconds'] != elapsed or saved['previous_elapsed_seconds'] != elapsed
                or type(extra) not in (int, float) or extra < 0
                or paused['total_active_seconds'] != elapsed + extra):
            raise ValueError('paused attempt identity or accumulated runtime differs')
        elapsed = paused['total_active_seconds']
        if not 0 <= elapsed < limit_seconds('T10'):
            raise ValueError('paused attempt has no physical budget remaining')
        pause_evidence = dict(pause=artifact(pause_record), previous_resume_plan=artifact(saved_path),
                              interrupted_retry_active_seconds=extra)
    prepared = run_seed(item, seed, work, orfs, 'baseline', memory_gib=40,
                        allow_swap=True, prepare_only=True, threads=threads)
    inputs = prepared['inputs']
    if inputs['orfs_revision'] != old['orfs_revision'] or inputs['openroad'] != old['openroad']:
        raise ValueError('physical tool version changed since the checkpoint')
    root = Path(orfs) / 'flow/results/asap7' / item['pe']
    source = root / old['variant']
    target = root / inputs['variant']
    if source == target or target.exists():
        raise ValueError('resume requires a new empty implementation variant')
    records = {name: artifact(source / name) for name in ('5_1_grt.odb', '5_1_grt.sdc', 'route.guide')}
    target.mkdir(parents=True)
    for name, record in records.items():
        shutil.copy2(record['path'], target / name)
        if artifact(target / name)['sha256'] != record['sha256']:
            raise ValueError('copied checkpoint differs')
    inputs['checkpoint_resume'] = dict(original_inputs=artifact(ip), original_completion=artifact(pp),
                                      original_budget=artifact(budget_path), checkpoints=records,
                                      prior_active_seconds=elapsed, detailed_route_threads=threads)
    if pause_evidence:
        inputs['checkpoint_resume']['user_pause'] = pause_evidence
    input_path = Path(prepared['input_path'])
    write(input_path, inputs)
    directory = Path(work) / item['model'] / f'seed{seed}'
    write(directory / 'active_attempt.json', dict(inputs='inputs40.json', physical='baseline40.json'))
    command = prepared['command']
    if command[-2:] != ['route', 'do-finish']:
        raise ValueError('unexpected physical command')
    command = command[:-2] + ['do-5_2_route', 'do-5_3_fillcell', 'do-5_route', 'do-5_route.sdc', 'do-finish']
    data = dict(command=command, inputs=inputs, input_path=str(input_path), marker=prepared['marker'],
                previous_elapsed_seconds=elapsed, remaining_seconds=limit_seconds('T10')-elapsed,
                result_dir=str(target), directory=str(directory))
    write(directory / 'resume_plan.json', data)
    return data


def resume(item, seed, work, orfs, previous, *, threads=1, pause_record=None):
    data = plan(item, seed, work, orfs, previous, threads=threads, pause_record=pause_record)
    directory = Path(data['directory'])
    unit = next(arg.split('=', 1)[1] for arg in data['command'] if arg.startswith('--unit='))
    assert_serial()
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (directory / 'baseline40.log').open('x') as log:
        process = subprocess.Popen(data['command'], stdout=log, stderr=subprocess.STDOUT,
                                   env=os.environ | {'MALLOC_ARENA_MAX': '2'})
        runtime = monitor(unit, directory / 'runtime40.json', process,
                          physical_identity=('T10', item['source_sha256'], seed),
                          physical_elapsed_seconds=data['previous_elapsed_seconds'])
    output = Path(data['result_dir'])
    paths = [output / ('6_final.' + ext) for ext in ('odb', 'spef', 'sdc', 'v')]
    code = runtime.get('exit_code', 1)
    if code == 0 and not all(p.is_file() for p in paths):
        code = 1
    record = dict(status='physical_flow_completed_not_qualified' if code == 0 else 'failed_40g_requires_adjudication',
                  model=item['model'], layout_seed=seed, exit_code=code,
                  inputs_sha256=artifact(data['input_path'])['sha256'],
                  artifacts={p.name: artifact(p) for p in paths if p.exists()},
                  resource_policy=POLICY, runtime=artifact(directory / 'runtime40.json'),
                  checkpoint_resume=artifact(directory / 'resume_plan.json'), resumed_utc=started)
    write(Path(data['marker']), record)
    return record
