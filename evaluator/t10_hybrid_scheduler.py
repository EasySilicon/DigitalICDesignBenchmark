#!/usr/bin/env python3
"""Durable serial dispatch of independent, resource-bounded T10 workers.

The controller is outside every worker's cgroup. A failed worker always becomes
a recorded terminal attempt; it cannot kill the queue or make pending jobs look
complete. Only workers hold the shared EDA lock, including after controller exit.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

from t10_hybrid_ppa import REPO, artifact, check, external_directory, score, write


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def properties(unit):
    result = subprocess.run(['systemctl', '--user', 'show', unit,
                             '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result',
                             '-p', 'ExecMainCode', '-p', 'ExecMainStatus',
                             '-p', 'MemoryPeak', '-p', 'CPUUsageNSec'],
                            text=True, capture_output=True, check=False, timeout=15)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def active(props):
    return props.get('ActiveState') in ('active', 'activating', 'deactivating')


def available_memory():
    """Use reclaimable host availability, not just free pages or swap size."""
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('host MemAvailable is unavailable')


def admit(config, notify, *, sample=available_memory, sleep=time.sleep):
    # The caller supplies host-specific headroom; it is not a new DUT budget.
    required = config.get('host_admission_available_bytes')
    if required is None:
        return
    if type(required) is not int or required <= 0:
        raise ValueError('invalid host memory admission threshold')
    while True:
        available = sample()
        if available >= required:
            return
        notify(dict(stage='waiting_host_memory', available_bytes=available,
                    required_available_bytes=required))
        sleep(5)


def terminal_result(label, directory, runtime):
    """Prefer the actual unit failure over incomplete or stale output files."""
    result = runtime.get('Result')
    if result == 'oom-kill':
        return dict(label=label, status='worker_oom_requires_attribution', runtime=runtime)
    if result in ('timeout', 'watchdog'):
        return dict(label=label, status='worker_watchdog_incomplete', runtime=runtime)
    completed = directory / 'measurement.json'
    if runtime.get('controller_returncode', 0) == 0 and result in ('success', None, '') and completed.exists():
        return dict(label=label, status='measured', measurement=artifact(completed), runtime=runtime)
    failure = directory / 'failure.json'
    if failure.exists():
        data = json.loads(failure.read_text())
        if data.get('label') != label:
            raise ValueError('worker failure identity mismatch')
        return dict(data, runtime=runtime)
    return dict(label=label, status='worker_failed_requires_attribution', runtime=runtime,
                reason='Worker exited without a complete measurement or failure receipt.')


def isolated(job, directory, config, notify):
    identity = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:16]
    unit = 't10-v16-worker-' + identity + '.service'
    request = dict(job=job, output=str(directory), compiler_root=config.get('compiler_root'),
                   orfs=config['orfs'], grade_lock=config['grade_lock'])
    path = directory / 'worker_request.json'
    if path.exists() and json.loads(path.read_text()) != request:
        raise ValueError('existing worker request differs; use a fresh attempt directory')
    if not path.exists():
        write(path, request)
    launch = directory / 'worker_launch.json'
    previous = properties(unit)
    if launch.exists():
        receipt = json.loads(launch.read_text())
        if receipt['request'] != artifact(path) or receipt['unit'] != unit:
            raise ValueError('worker launch identity changed')
        if not active(previous):
            # Never silently repeat a terminal attempt after controller restart.
            runtime = json.loads((directory / 'worker_runtime.json').read_text()) if (directory / 'worker_runtime.json').exists() else previous
            return terminal_result(job['label'], directory, runtime)
        notify(dict(label=job['label'], stage='reattached_existing_worker', unit=unit))
        while active(properties(unit)):
            notify(dict(label=job['label'], stage='waiting_existing_worker', unit=unit))
            time.sleep(2)
        runtime = properties(unit)
        write(directory / 'worker_runtime.json', runtime)
        return terminal_result(job['label'], directory, runtime)
    admit(config, lambda row: notify(dict(row, label=job['label'], unit=unit)))
    # Match the already-authorized 40-GiB worker policy. The watchdog is an
    # infrastructure backstop, not an extra candidate scoring deadline.
    from run_t10_candidate_40g import POLICY
    command = ['systemd-run', '--user', '--wait', '--pipe', '--unit=' + unit,
               '-p', f'MemoryMax={POLICY["memory_max_bytes"]}',
               '-p', 'MemorySwapMax=infinity', '-p', 'OOMPolicy=kill',
               '-p', f'CPUQuota={POLICY["cpu_threads"] * 100}%', '-p', 'TasksMax=512',
               '-p', f'RuntimeMaxSec={config.get("worker_watchdog_seconds", 28800)}',
               sys.executable, '-u', str(Path(__file__).resolve()), '--worker', str(path)]
    write(launch, dict(unit=unit, request=artifact(path), command=command, started_utc=utc()))
    notify(dict(label=job['label'], stage='worker_dispatched', unit=unit))
    with (directory / 'worker.log').open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            notify(dict(label=job['label'], stage='worker_active', unit=unit))
            time.sleep(2)
    runtime = properties(unit)
    runtime.update(controller_returncode=child.returncode, ended_utc=utc())
    write(directory / 'worker_runtime.json', runtime)
    return terminal_result(job['label'], directory, runtime)


def run(config, *, dispatch=isolated):
    labels = [job['label'] for job in config['jobs']]
    if (len(labels) != len(set(labels)) or any(
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', s) or s in ('.', '..') for s in labels)):
        raise ValueError('unique safe job labels are required')
    out = external_directory(config['output'])
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'controller.lock').open('a+') as controller_lock:
        fcntl.flock(controller_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config_path = out / 'campaign.json'
        if config_path.exists() and json.loads(config_path.read_text()) != config:
            raise ValueError('campaign inputs changed; preserve this attempt')
        if not config_path.exists():
            write(config_path, config)
        state_path = out / 'progress.json'
        results = json.loads(state_path.read_text()) if state_path.exists() else []
        if len({r['label'] for r in results}) != len(results) or any(r['label'] not in labels for r in results):
            raise ValueError('invalid persisted queue state')

        def status(row):
            write(out / 'status.json', dict(row, heartbeat_utc=utc(), queue_finished=False,
                                          completed_attempts=len(results), total_jobs=len(labels)))

        def update_scores():
            try:
                if config.get('reference_measurement') or config.get('reference_label'):
                    reference_path = Path(config['reference_measurement']) if config.get('reference_measurement') else out / config['reference_label'] / 'measurement.json'
                    if not reference_path.exists():
                        return set()
                    reference = json.loads(reference_path.read_text())
                else:
                    from t10_hybrid_ppa import official_reference
                    reference = official_reference()
                scores = []
                for row in results:
                    if row['status'] == 'measured':
                        check(row['measurement'])
                        data = json.loads(Path(row['measurement']['path']).read_text())
                        scores.append(dict(label=row['label'], ppa_score=score(data, reference), measurement=row['measurement']))
                write(out / 'scores.json', scores)
                return {row['label'] for row in scores}
            except Exception:
                write(out / 'scoring_error.json', dict(error=traceback.format_exc()))
                return set()

        for job in config['jobs']:
            if any(r['label'] == job['label'] for r in results):
                continue
            directory = out / job['label']
            directory.mkdir(exist_ok=True)
            status(dict(label=job['label'], stage='dispatching'))
            try:
                record = dispatch(job, directory, config, status)
            except Exception:
                record = dict(label=job['label'], status='dispatch_failed_requires_attribution', error=traceback.format_exc())
            results.append(record)
            write(state_path, results)
            # Scoring/reporting failures are separate from dispatch failures.
            # In particular, a malformed report cannot stop later workers.
            update_scores()
        scored_labels = update_scores()
        unresolved = [r['label'] for r in results if
                      r['status'] != 'power_compile_timeout_zero' and r['label'] not in scored_labels]
        write(out / 'status.json', dict(stage='finished_with_unresolved' if unresolved else 'completed',
                                      queue_finished=True, all_scored=not unresolved, unresolved=unresolved,
                                      measured=sum(r['status'] == 'measured' for r in results),
                                      total_jobs=len(labels), heartbeat_utc=utc()))
        return results


def worker(request_path):
    from power_compile_budget import PowerCompileTimeout
    from t10_hybrid_measure import measure
    request = json.loads(request_path.read_text())
    job = request['job']
    directory = external_directory(request['output'])
    try:
        write(directory / 'worker_phase.json', dict(stage='waiting_grade_lock', utc=utc()))
        with Path(request['grade_lock']).open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            write(directory / 'worker_phase.json', dict(stage='measuring', utc=utc()))
            measure(job, directory, request.get('compiler_root'), request['orfs'])
        write(directory / 'worker_phase.json', dict(stage='completed', utc=utc()))
        return 0
    except PowerCompileTimeout:
        write(directory / 'failure.json', dict(label=job['label'], status='power_compile_timeout_zero',
                                              ppa_score=0., error=traceback.format_exc()))
        return 124
    except Exception:
        write(directory / 'failure.json', dict(label=job['label'], status='measurement_failed_requires_attribution',
                                              error=traceback.format_exc()))
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--campaign', type=Path)
    group.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        raise SystemExit(worker(args.worker))
    run(json.loads(args.campaign.read_text()))
