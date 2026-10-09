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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ppa_aggregate import aggregate, expected_result_dir, source_hash
from t11_sram import prepare, contract, sha256, validated_mapping
from score_run import score_run, weighted_suite_score, load_rules
from delivery_check import read_result, check_normal
from benchmark.run_t08_comparison import command, TOOL_PATH


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def publish(repo: Path, model: str, record: dict, trial: Path):
    """Replace only this task, keeping every other task and raw trial immutable."""
    canonical = {'kimi-k3': '/mnt/ubu_3T/ic_bcmk_trials/kimi_k3_256k_20261004',
                 'glm-5.3-flash': '/mnt/ubu_3T/ic_bcmk_trials/claude_glm_5_3_flash_20261005'}
    results = repo / 'results' / model
    backup = trial / 'publication_backup' / model
    backup.mkdir(parents=True, exist_ok=True)
    for path in (results / 'T08.json', results / 'summary.json', Path(canonical[model]) / 'summary.json'):
        if path.exists():
            label = ('canonical_' if path.parent == Path(canonical[model]) else '') + path.name
            if not (backup / label).exists():
                shutil.copy2(path, backup / label)
    old = json.loads((results / 'T08.json').read_text())
    old.update(record)
    write(results / 'T08.json', old)
    for path in (results / 'summary.json', Path(canonical[model]) / 'summary.json'):
        summary = json.loads(path.read_text())
        rows = summary['tasks']
        for row in rows:
            if row['task_id'] == 'T08':
                row.update(record)
        totals = {key: sum(row.get(key) or 0 for row in rows) for key in
                  ('functional_total', 'ppa_score', 'time_score', 'display_score')}
        summary.update(functional_total_sum=totals['functional_total'],
            functional_score_sum=totals['functional_total'], ppa_score_sum=totals['ppa_score'],
            ppa_score_sum_for_available_tasks=totals['ppa_score'],
            time_score_sum=totals['time_score'], time_score_sum_for_available_tasks=totals['time_score'],
            display_score_sum=totals['display_score'],
            display_score_subtotal_with_unscored_components_omitted=totals['display_score'],
            full_functional_task_count=sum(row.get('full_functional_pass') is True for row in rows),
            result_revision_date=dt.datetime.now().astimezone().date().isoformat(), ranking_eligible=False)
        weighted = weighted_suite_score({row['task_id']: row.get('display_score') for row in rows})
        summary.update(weighted)
        summary.update(weighted_display_score_with_unscored_components_omitted=weighted['weighted_display_score'],
                       weighted_task_contributions=weighted['weighted_contributions'])
        summary['pending_components'] = {row['task_id']: [key for key in
            ('functional_total', 'ppa_score', 'time_score') if row.get(key) is None] for row in rows
            if any(row.get(key) is None for key in ('functional_total', 'ppa_score', 'time_score'))}
        summary['complete_display_score_task_count'] = len(rows) - len(summary['pending_components'])
        summary['totals_complete'] = not summary['pending_components']
        write(path, summary)
    table = repo / 'results/model-score-comparison.md'
    if table.exists():
        models = ('gpt-6-astra', 'gpt-6.1-sol', 'gpt-6-sol', 'kimi-k3', 'deepseek-flash', 'glm-5.3-flash')
        data = [json.loads((repo / 'results' / name / 'summary.json').read_text()) for name in models]
        weights = load_rules()['task_weights']
        lines = []
        for line in table.read_text().splitlines():
            task = line.split('|')[1].strip() if line.startswith('| T') else None
            if task in weights:
                values = []
                for summary in data:
                    row = next(row for row in summary['tasks'] if row['task_id'] == task)
                    value = row.get('display_score')
                    pending = any(row.get(key) is None for key in ('ppa_score', 'time_score'))
                    values.append('未测' if value is None else f'{value:.2f}' + ('¹' if pending else ''))
                line = f'| {task} | {weights[task]:.2f} | ' + ' | '.join(values) + ' |'
            elif line.startswith('| **已评分加权小计'):
                line = '| **已评分加权小计 /105** | **1.00** | ' + ' | '.join(f'{s.get("weighted_display_score", s["weighted_display_score_with_unscored_components_omitted"]):.2f}' for s in data) + ' |'
            elif line.startswith('| 已评分直接加总'):
                line = '| 已评分直接加总 /1050 | — | ' + ' | '.join(f'{s.get("display_score_sum", s["display_score_subtotal_with_unscored_components_omitted"]):.2f}' for s in data) + ' |'
            lines.append(line)
        table.write_text('\n'.join(lines) + '\n')


def delivery(trial: Path, output: Path):
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
    try:
        if not os.access(workspace / 'run.sh', os.X_OK):
            raise ValueError('run.sh missing or not executable')
        if not (workspace / 'README.md').is_file() or not (workspace / 'verif').is_dir():
            raise ValueError('README.md or verif/ missing')
        for index in (1, 2):
            name = 'ic-bcmk-t08-delivery-' + str(os.getpid()) + '-' + str(index)
            cmd = command(sandbox, 'kimi', name, '', shell='BENCH_SEED=20261007 timeout --signal=INT --kill-after=10s 600s ./run.sh')
            try:
                with (output / f'delivery_run{index}.log').open('w') as log:
                    result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=630)
                if result.returncode:
                    raise ValueError(f'candidate run.sh exited {result.returncode}; see delivery_run{index}.log')
                report = read_result(workspace / 'results.json')
                tests.append(check_normal(report))
                write(output / f'delivery_result{index}.json', report)
            finally:
                subprocess.run(['docker', 'stop', '--timeout', '2', name], capture_output=True)
            if index == 1:
                (workspace / 'results.json').unlink()
        if tests[0] != tests[1]:
            raise ValueError('same-seed self-check results changed')
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        findings.append(str(error))
    report = {'delivery_qualified': not findings, 'findings': findings,
              'self_check_tests': len(tests[0]) if tests else 0, 'execution': 'isolated Docker; not host'}
    write(output / 'delivery.json', report)
    return report


def run(trial: Path, orfs: Path, repo: Path):
    output = trial / 'ppa_grading'
    output.mkdir(exist_ok=False)
    manifest = json.loads((trial / 'run_manifest.json').read_text())
    functional = json.loads((trial / 'summary.json').read_text())
    state = {'task': 'T08', 'status': 'running', 'selected_seeds': [11, 29, 47], 'completed_seeds': []}
    def update(stage, **fields):
        state.update(stage=stage, updated_utc=dt.datetime.now(dt.timezone.utc).isoformat(), **fields)
        write(output / 'state.json', state)
        write(trial / 'status.json', {'status': 'ppa_grading' if state['status'] == 'running' else state['status'],
              'stage': stage, 'completed_seeds': state['completed_seeds'], 'updated_utc': state['updated_utc'],
              'error': state.get('error')})
        print('PPA_GRADING ' + json.dumps(state), flush=True)
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PATH': TOOL_PATH, 'PYTHONDONTWRITEBYTECODE': '1'}
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
        delivery_report = delivery(trial, output)
        groups = {g['id']: {'cases_total': len(g['cases']), 'cases_passed': sum(
                  functional['cases'][str(case)]['passed'] for case in g['cases']), 'safety_violation': False}
                  for g in functional['test_groups']}
        payload = {'task_id': 'T08', 'groups': groups,
                   'elapsed_seconds': manifest['previous_submission_elapsed_seconds'] + functional['elapsed_seconds'],
                   'time_limit_seconds': manifest['cumulative_time_limit_seconds'],
                   'delivery_qualified': delivery_report['delivery_qualified'],
                   'candidate_delivery_error_count': 0}
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
            with Path('/mnt/ubu_3T/ic_bcmk_trials/grade.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                for seed in (11, 29, 47):
                    while int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                   if line.startswith('MemAvailable:'))) < 50 * 1024 * 1024:
                        update(f'waiting_for_50GiB_seed{seed}')
                        time.sleep(30)
                    route, power = output / f'seed{seed}/route', output / f'seed{seed}/power'
                    execute(f'seed{seed}_route', [sys.executable, str(ROOT / 'evaluator/ppa_probe.py'), 'T08', str(submission),
                        '--orfs-root', str(orfs), '--output-dir', str(route), '--seed', str(seed), '--t08-sram-mapping', str(mapped)])
                    route_record = json.loads((route / 'result.json').read_text())
                    execute(f'seed{seed}_power', [sys.executable, str(ROOT / 'evaluator/t08_power_probe.py'),
                        '--flow-result-dir', str(expected_result_dir(route_record['report'])), '--output-dir', str(power),
                        '--sram-route', str(route / 'result.json')])
                    pairs.append((route / 'result.json', power / 'result.json'))
                    state['completed_seeds'].append(seed)
                    update(f'seed{seed}_complete')
            measurement = aggregate('T08', submission, pairs, (11, 29, 47))
            write(output / 'measurement.json', measurement)
            baseline = json.loads((ROOT / 'benchmark/ppa-baselines.json').read_text())['tasks']['T08']
            payload.update(ppa_measurement=measurement, ppa_reference=baseline)
        write(output / 'score_input.json', payload)
        score = score_run(payload)
        if measurement is not None and not score['ppa_eligible']:
            raise RuntimeError('PPA provenance mismatch; do not publish fake zero score')
        score.update(model=manifest['model'], legacy_task_id='T11', suite_id='ic-delivery-rtl-v0.3',
            elapsed_seconds=payload['elapsed_seconds'], time_limit_seconds=payload['time_limit_seconds'],
            additional_phase_elapsed_seconds=functional['elapsed_seconds'],
            previous_trial=manifest['previous_trial'], trial_kind='ppa_continuation_60m', ranking_eligible=False,
            score_status='scored' if delivery_report['delivery_qualified'] else 'delivery_attribution_pending',
            grade_phase='scored' if delivery_report['delivery_qualified'] else 'delivery_attribution_pending',
            judge_revision=functional.get('judge_revision'), source_sha256=source_digest,
            ppa_measurement_file=str(output / 'measurement.json') if measurement else None,
            trial_directory=str(trial), eda=functional.get('eda'),
            note='Additional 60-minute PPA continuation after prior 90-minute pilot; cumulative budget 150 minutes. Not a uniform-budget ranking result.')
        write(output / 'score.json', score)
        # Fatal delivery findings need evaluator attribution before any fixed -5
        # deduction. Preserve numeric independent RTL/PPA results, no invention.
        publish(repo, 'kimi-k3', score, trial)
        write(trial / 'final_score.json', score)
        write(trial / 'status.json', {'status': 'scored', 'functional_total': score['functional_total'],
                                    'ppa_score': score['ppa_score'], 'display_score': score['display_score']})
        update('complete', status='scored' if delivery_report['delivery_qualified'] else 'delivery_attribution_pending')
    except BaseException as error:
        update('incomplete_pending_attribution', status='grading_incomplete', error=str(error))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--orfs', type=Path, required=True)
    parser.add_argument('--publish-repo', type=Path, required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.orfs.resolve(), args.publish_repo.resolve())


if __name__ == '__main__':
    main()
