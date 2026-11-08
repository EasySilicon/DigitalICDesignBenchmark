#!/usr/bin/env python3
"""Host-only candidate PPA grading; never promotes/freezes a reference.

All three layout seeds are measured even with negative timing slack. Candidate
handoff scripts run only in a separate Docker container, never on the host.
Infrastructure failures stay pending attribution, not fabricated zero scores.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ppa_aggregate import expected_result_dir, source_hash
from aggregate_with_power_budget import aggregate
from t11_sram import prepare, contract, sha256, validated_mapping
from score_run import weighted_suite_score, load_rules
from result_publication import final_summary
from score_with_power_budget import score_run
from power_compile_budget import TIMEOUT_EXIT_CODE, validate_timeout
import physical_budget
from physical_grading import read_receipt
from delivery_check import read_result, check_normal, inspect_contract, DEFAULT_DELIVERY_SEEDS
from benchmark.runner.adapters import AdapterRuntime
from benchmark.runner.config import load_config
from benchmark.runner.container import docker_command


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def publish(repo: Path, model: str, record: dict, trial: Path):
    """Publish one task inside the sole final summary; archive raw inputs externally."""
    path=repo/'results'/model/'summary.json'
    original=json.loads(path.read_text())
    updated=dict(record,full_functional_pass=record['functional_total']==50)
    published=final_summary(original,{'T08':updated})
    backup=trial/'publication_backup'/model
    backup.mkdir(parents=True,exist_ok=True)
    if not (backup/'summary.json').exists():shutil.copy2(path,backup/'summary.json')
    write(path,published)


def delivery(trial: Path, output: Path, runner_config=None):
    if runner_config is None:
        raise RuntimeError('isolated delivery replay requires --runner-config with the installed tool image and mounts')
    hardware = yaml.safe_load((ROOT/'benchmark/manifest.yaml').read_text())['hardware_limit']
    assessment = inspect_contract(trial / 'workspace')
    sandbox = output / 'delivery_sandbox'
    workspace = sandbox / 'workspace'
    workspace.mkdir(parents=True)
    for folder in ('agent_home', 'empty_skills', 'tmp'):
        (sandbox / folder).mkdir()
    for entry in (trial / 'workspace').iterdir():
        if entry.name in {'benchmark', 'ppa', 'build', 'obj_dir', '.git', 'results.json',
                          'PROMPT.md', 'TRIAL_CLOCK.json'} or entry.name.startswith('ppa_'):
            continue
        if entry.is_dir():
            shutil.copytree(entry, workspace / entry.name, symlinks=True,
                           ignore=shutil.ignore_patterns('build*', 'obj_dir', '*.log', '*.vcd', '__pycache__'))
        elif entry.is_file() or entry.is_symlink():
            shutil.copy2(entry, workspace / entry.name, follow_symlinks=False)
    findings, tests = [], []
    execution_started = False
    try:
        if not os.access(workspace / 'run.sh', os.X_OK):
            raise ValueError('run.sh missing or not executable')
        if not (workspace / 'README.md').is_file() or not (workspace / 'verif').is_dir():
            raise ValueError('README.md or verif/ missing')
        for seed in DEFAULT_DELIVERY_SEEDS:
            pair=[]
            for index in (1, 2):
                execution_started=True
                name=f'ic-bcmk-t08-delivery-{os.getpid()}-{seed}-{index}'
                runtime=AdapterRuntime(f'BENCH_SEED={seed} timeout --signal=INT --kill-after=10s 600s ./run.sh',
                                       environment=('CCACHE_DIR=/tmp/ccache',))
                cmd=docker_command(runner_config,sandbox,runtime,name,
                                   cpus=hardware['vcpu'],memory_gib=hardware['ram_gib'])
                result_path=workspace/'results.json'
                result_path.unlink(missing_ok=True)
                try:
                    log_path=output/f'delivery_seed{seed}_run{index}.log'
                    with log_path.open('w') as log:
                        result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=630)
                    if result.returncode:
                        raise ValueError(f'candidate run.sh exited {result.returncode}; see {log_path.name}')
                    report=read_result(result_path)
                    pair.append(check_normal(report))
                    write(output/f'delivery_seed{seed}_result{index}.json',report)
                finally:
                    subprocess.run(['docker','stop','--timeout','2',name],capture_output=True)
            if pair[0]!=pair[1]:
                raise ValueError(f'same-seed self-check results changed for seed {seed}')
            tests.extend(pair[0])
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        findings.append(str(error))
        if execution_started:
            assessment['errors'].append(dict(root_cause='self_check_execution',
                detail=str(error), attribution='pending'))
    findings = list(dict.fromkeys(
        ['Missing deliverable: ' + item for item in assessment['missing_deliverables']] +
        [error['detail'] for error in assessment['errors']] + findings))
    report = {'delivery_qualified': not findings, 'findings': findings,
              'delivery_assessment': assessment,
              'self_check_tests': len(tests), 'execution': 'isolated Docker; not host',
              'delivery_seeds': list(DEFAULT_DELIVERY_SEEDS), 'replays_per_seed': 2}
    write(output / 'delivery.json', report)
    return report


def result_model(manifest: dict) -> str:
    name = manifest['model']
    if name == 'kimi-code/k3-256k':
        return 'kimi-k3'
    if name not in {'gpt-6-astra', 'gpt-6-sol', 'gpt-6.1-sol', 'gpt-5.6-sol',
                    'glm-5.3-flash', 'deepseek-flash'}:
        raise ValueError(f'unknown result model: {name}')
    return name


def candidate_clock(manifest: dict, functional: dict) -> tuple[float, float]:
    """Use candidate development time only; independent EDA is excluded."""
    elapsed = manifest.get('previous_submission_elapsed_seconds', 0) + functional['elapsed_seconds']
    limit = manifest.get('cumulative_time_limit_seconds', manifest['time_limit_seconds'])
    if elapsed < 0 or limit <= 0:
        raise ValueError('invalid candidate clock')
    return elapsed, limit


def run(trial: Path, orfs: Path, repo: Path, runner_config=None):
    output = trial / 'ppa_grading'
    output.mkdir(exist_ok=False)
    manifest = json.loads((trial / 'run_manifest.json').read_text())
    functional = json.loads((trial / 'summary.json').read_text())
    model = result_model(manifest)
    elapsed, limit = candidate_clock(manifest, functional)
    state = {'task': 'T08', 'status': 'running', 'selected_seeds': [11, 29, 47], 'completed_seeds': []}
    def update(stage, **fields):
        state.update(stage=stage, updated_utc=dt.datetime.now(dt.timezone.utc).isoformat(), **fields)
        write(output / 'state.json', state)
        write(trial / 'status.json', {'status': 'ppa_grading' if state['status'] == 'running' else state['status'],
              'stage': stage, 'completed_seeds': state['completed_seeds'], 'updated_utc': state['updated_utc'],
              'error': state.get('error')})
        print('PPA_GRADING ' + json.dumps(state), flush=True)
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
    def execute(stage, cmd, timeout=3600):
        update(stage)
        with (output / (stage + '.log')).open('w') as log:
            subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
    try:
        if functional.get('functional_total') is None:
            raise RuntimeError('independent functional grading incomplete')
        submission = output / 'submission'
        (submission / 'rtl').mkdir(parents=True)
        shutil.copytree(trial / 'workspace/rtl', submission / 'rtl', dirs_exist_ok=True)
        source_digest = source_hash(submission)
        write(output / 'submission_receipt.json', {'source_sha256': source_digest, 'frozen_utc': dt.datetime.now(dt.timezone.utc).isoformat()})
        update('delivery_check')
        delivery_report = delivery(trial, output, runner_config)
        groups = {g['id']: {'cases_total': len(g['cases']), 'cases_passed': sum(
                  functional['cases'][str(case)]['passed'] for case in g['cases']), 'safety_violation': False}
                  for g in functional['test_groups']}
        payload = {'task_id': 'T08', 'groups': groups,
                   'elapsed_seconds': elapsed,
                   'time_limit_seconds': limit,
                   'delivery_qualified': delivery_report['delivery_qualified'],
                   'candidate_delivery_error_count': 0,
                   'candidate_source_sha256': source_digest, 'power_compile_records': []}
        if 'delivery_assessment' in delivery_report:
            payload['delivery_assessment'] = delivery_report['delivery_assessment']
        measurement = None
        if functional.get('full_functional_pass'):
            execute('power_environment_preflight', [sys.executable, str(ROOT / 'evaluator/t08_power_probe.py'), '--help'])
            update('mapping')
            mapped = output / 'mapped'
            prepare(submission, mapped)
            for module, stage in (('evaluator.t08_check', 'mapped_functional'), ('evaluator.t08_stress_check', 'mapped_stress')):
                execute(stage, [sys.executable, '-m', module, str(mapped), '--output', str(output / (stage + '.json'))], 2400)
            func = json.loads((output / 'mapped_functional.json').read_text())
            stress = json.loads((output / 'mapped_stress.json').read_text())
            if not func.get('full_functional_pass') or not stress.get('full_pass') or stress.get('passed_count') != 270:
                raise RuntimeError('SRAM-mapped RTL failed functional replay; attribution required')
            (mapped / 'evidence').mkdir()
            names = ('mapped_functional.json', 'mapped_stress.json')
            for name in names:
                shutil.copy2(output / name, mapped / 'evidence' / name)
            write(mapped / 'qualification.json', {'mapped_netlist_sha256': sha256(mapped / 'rtl/mapped.v'),
                'contract_sha256': contract()['contract_sha256'], 'functional_passes': 111, 'stress_passes': 270,
                'evidence_sha256': {'evidence/' + name: sha256(mapped / 'evidence' / name) for name in names}})
            validated_mapping(submission, mapped)
            pairs = []
            physical_records = []
            update('waiting_for_grading_lock')
            with Path('/mnt/ubu_3T/ic_bcmk_trials/grade.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                for seed in (11, 29, 47):
                    while int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                   if line.startswith('MemAvailable:'))) < 50 * 1024 * 1024:
                        update(f'waiting_for_50GiB_seed{seed}')
                        time.sleep(30)
                    route, power = output / f'seed{seed}/route', output / f'seed{seed}/power'
                    try:
                        execute(f'seed{seed}_route', [sys.executable, str(ROOT / 'evaluator/route_with_slang.py'), 'T08', str(submission),
                            '--orfs-root', str(orfs), '--output-dir', str(route), '--seed', str(seed), '--t08-sram-mapping', str(mapped)],timeout=None)
                    except subprocess.CalledProcessError as error:
                        if error.returncode != 124:
                            raise
                        if read_receipt(route/'physical_budget.json','T08',source_digest,seed)['status']!='timeout':
                            raise
                    physical_records.append(read_receipt(route/'physical_budget.json','T08',source_digest,seed))
                    if physical_records[-1]['status']=='timeout':
                        continue
                    route_record = json.loads((route / 'result.json').read_text())
                    try:
                        execute(f'seed{seed}_power', [sys.executable, str(ROOT / 'evaluator/power_probe_with_budget.py'),
                            '--task', 'T08', '--layout-seed', str(seed), '--candidate-source-sha256', source_digest,
                            '--flow-result-dir', str(expected_result_dir(route_record['report'])), '--output-dir', str(power),
                            '--sram-route', str(route / 'result.json')])
                    except subprocess.CalledProcessError as error:
                        if error.returncode!=TIMEOUT_EXIT_CODE:raise
                        record=json.loads((power/'power_compile.json').read_text())
                        validate_timeout(record,source_digest,seed,'T08')
                        payload['power_compile_records'].append(record)
                        break
                    payload['power_compile_records'].append(json.loads((power/'power_compile.json').read_text()))
                    pairs.append((route / 'result.json', power / 'result.json'))
                    state['completed_seeds'].append(seed)
                    update(f'seed{seed}_complete')
            payload.update(physical_policy=physical_budget.POLICY_ID,physical_records=physical_records)
            if pairs and not any(r['status']=='timeout' for r in payload['power_compile_records']):
                measurement = aggregate('T08', submission, pairs, (11, 29, 47),physical_records=physical_records)
                write(output / 'measurement.json', measurement)
                baseline = json.loads((ROOT / 'benchmark/ppa-baselines.json').read_text())['tasks']['T08']
                payload.update(ppa_measurement=measurement, ppa_reference=baseline)
        write(output / 'score_input.json', payload)
        score = score_run(payload)
        if payload['power_compile_records']:
            score.update(task_id='T08', candidate_source_sha256=source_digest,
                         power_compile_records=payload['power_compile_records'])
        if measurement is not None and not score['ppa_eligible']:
            raise RuntimeError('PPA provenance mismatch; do not publish fake zero score')
        score_status = 'delivery_attribution_pending' if score['delivery_penalty_status'] == 'pending' else 'scored'
        score.update(model=manifest['model'], legacy_task_id='T11', suite_id='ic-delivery-rtl-v0.3',
            elapsed_seconds=payload['elapsed_seconds'], time_limit_seconds=payload['time_limit_seconds'],
            trial_kind='pre_release_pilot', ranking_eligible=False,
            score_status=score_status,
            grade_phase=score_status,
            judge_revision=functional.get('judge_revision'), source_sha256=source_digest,
            ppa_measurement_file=str(output / 'measurement.json') if measurement else None,
            trial_directory=str(trial), eda=functional.get('eda'))
        if not functional.get('full_functional_pass'):
            score.update(ppa_status='zero_functional_gate',
                         ppa_zero_reason='Independent functional acceptance did not fully pass; PPA and time scores are zero under the frozen full-functional gate.',
                         failed_functional_cases=[int(case) for case, result in functional['cases'].items()
                                                  if not result['passed']])
        if manifest.get('previous_trial'):
            score.update(previous_trial=manifest['previous_trial'],
                         additional_phase_elapsed_seconds=functional['elapsed_seconds'])
        write(output / 'score.json', score)
        # Unattributed runtime faults keep the display total pending while
        # independently verified component scores remain available.
        publish(repo, model, score, trial)
        write(trial / 'final_score.json', score)
        write(trial / 'status.json', {'status': 'scored', 'functional_total': score['functional_total'],
                                    'ppa_score': score['ppa_score'], 'display_score': score['display_score']})
        update('complete', status=score_status)
    except BaseException as error:
        update('incomplete_pending_attribution', status='grading_incomplete', error=str(error))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--orfs', type=Path, required=True)
    parser.add_argument('--publish-repo', type=Path, required=True)
    parser.add_argument('--runner-config', type=Path, required=True,
                        help='current runner configuration for isolated self-check tools and mounts')
    args = parser.parse_args()
    run(args.root.resolve(), args.orfs.resolve(), args.publish_repo.resolve(), load_config(args.runner_config))


if __name__ == '__main__':
    main()
