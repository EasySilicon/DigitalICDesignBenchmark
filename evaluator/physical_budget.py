"""Evaluator-owned per-seed physical deadline and retained-result policy."""
import datetime as dt
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time

LIMIT_SECONDS = 3600
POLICY_ID = 'physical-wall-3600s-retain-results-v1'
SEEDS = (11, 29, 47)
TIMEOUT_EXIT_CODE = 124


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def receipt(task, source, seed, elapsed, status, **fields):
    result = dict(policy_id=POLICY_ID, limit_seconds=LIMIT_SECONDS, task_id=task,
                candidate_source_sha256=source, layout_seed=seed,
                elapsed_seconds=elapsed, status=status)
    result.update(fields)
    return result


def stop_scope(unit):
    # systemd-run moves the EDA processes out of the launcher's process group.
    result = subprocess.run(['systemctl', '--user', 'kill', '--kill-whom=all',
                    '--signal=SIGKILL', unit], capture_output=True, check=False)
    if result.returncode:
        state=subprocess.run(['systemctl','--user','show',unit,'-p','ActiveState','--value'],
                             capture_output=True,text=True,check=False).stdout.strip()
        if state in ('active','activating'):
            raise RuntimeError('failed to terminate physical scope '+unit)


def run(command, *, task, source, seed, record_path, seconds=LIMIT_SECONDS, **options):
    """Run a complete synthesis-to-final-report command in its own session."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('invalid physical deadline')
    started = time.monotonic()
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    process = subprocess.Popen(command, start_new_session=True, **options)
    status = 'error'
    try:
        try:
            code = process.wait(timeout=max(0, seconds-(time.monotonic()-started)))
            status = 'completed' if code == 0 else 'error'
        except subprocess.TimeoutExpired:
            status = 'timeout'
            unit=next((str(arg).split('=',1)[1] for arg in command if str(arg).startswith('--unit=')),None)
            if unit:
                stop_scope(unit)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            code = TIMEOUT_EXIT_CODE
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    finally:
        save(record_path, receipt(task, source, seed, time.monotonic()-started, status,
             started_utc=started_utc, ended_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
             process_group_terminated=status == 'timeout',
             **({'limit_seconds': seconds} if seconds != LIMIT_SECONDS else {})))
    return subprocess.CompletedProcess(command, code)


def validate_records(records, source, task, *, complete=True):
    if not isinstance(records, list):
        raise ValueError('physical records must be a list')
    seen = set()
    for row in records:
        if not isinstance(row,dict):
            raise ValueError('physical receipt must be an object')
        seed = row.get('layout_seed')
        elapsed = row.get('elapsed_seconds')
        if (type(seed) is not int or seed not in SEEDS or seed in seen
                or row.get('policy_id') != POLICY_ID or row.get('limit_seconds') != LIMIT_SECONDS
                or row.get('task_id') != task or not source
                or row.get('candidate_source_sha256') != source
                or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0
                or row.get('status') not in ('completed', 'timeout')):
            raise ValueError('invalid physical deadline receipt')
        if row['status'] == 'timeout' and (elapsed < LIMIT_SECONDS or
                row.get('process_group_terminated') is not True):
            raise ValueError('unconfirmed physical timeout')
        if row['status'] == 'completed' and elapsed > LIMIT_SECONDS:
            raise ValueError('physical result completed after its deadline')
        seen.add(seed)
    if complete and seen != set(SEEDS):
        raise ValueError('physical assessment requires a terminal receipt for all three seeds')
    return {r['layout_seed'] for r in records if r['status'] == 'timeout'}


def attach(measurement, records):
    result = dict(measurement, physical_policy=POLICY_ID, physical_records=records)
    if any(r['status'] == 'timeout' for r in records):
        result['measurement_status'] = 'physical_timeout_retained_results'
    return result


def timed_out(directory):
    """A terminal timeout must be preserved, never silently retried."""
    path=Path(directory)/'physical_budget.json'
    if not path.exists():
        return False
    row=json.loads(path.read_text())
    if row.get('status')!='timeout':
        return False
    validate_records([row],row.get('candidate_source_sha256'),row.get('task_id'),complete=False)
    return True


def partial_provenance_valid(task, measurement, reference, records, source):
    """Validate real retained seeds without fabricating three replacement rows."""
    from score_run import expected_ppa_parameters, ppa_provenance_valid
    timeouts = validate_records(records, source, task)
    if not timeouts or not ppa_provenance_valid(task, reference, reference):
        return False
    if (measurement.get('physical_policy') != POLICY_ID or
            measurement.get('physical_records') != records or
            measurement.get('measurement_status') != 'physical_timeout_retained_results' or
            measurement.get('source_sha256') != source or measurement.get('task_id') != task or
            measurement.get('parameter_set') != expected_ppa_parameters(task) or
            measurement.get('routed') is not True or
            any(measurement.get(k) != reference.get(k) for k in
                ('workload_id', 'workload_parameters')) or
            not isinstance(measurement.get('workload_sha256'), str) or
            len(measurement['workload_sha256']) != 64):
        return False
    rows = measurement.get('per_seed')
    completed = set(SEEDS)-timeouts
    if not isinstance(rows, list) or not rows or sorted(r.get('layout_seed', -1) for r in rows) != sorted(completed):
        return False
    if task == 'T10' and (measurement.get('measurement_scope') != 'single_pe' or
            any(r.get('measurement_scope') != 'single_pe' for r in rows)):
        return False
    for row in rows:
        if (any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k]) or row[k] <= 0
                for k in ('area_um2', 'delay_ns', 'energy_per_op_pj')) or
                any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k])
                    for k in ('setup_worst_slack_ns', 'hold_worst_slack_ns', 'annotation_fraction')) or
                row['annotation_fraction'] < .95 or type(row.get('drc_violations')) is not int or
                row['drc_violations'] < 0):
            return False
    expected = {k: statistics.median(r[k] for r in rows)
                for k in ('area_um2', 'delay_ns', 'energy_per_op_pj')}
    expected.update(setup_worst_slack_ns=min(r['setup_worst_slack_ns'] for r in rows),
        hold_worst_slack_ns=min(r['hold_worst_slack_ns'] for r in rows),
        drc_violations=max(r['drc_violations'] for r in rows),
        annotation_fraction=min(r['annotation_fraction'] for r in rows))
    return all(measurement.get(k) == v for k, v in expected.items())


def score_retained(payload, result, rules):
    import score_run as native
    task = payload['task_id']
    records = payload.get('physical_records', [])
    source = payload.get('candidate_source_sha256')
    timeouts = validate_records(records, source, task)
    result.update(physical_policy=POLICY_ID, physical_records=records,
                  physical_timed_out_seeds=sorted(timeouts),candidate_source_sha256=source)
    measurement = payload.get('ppa_measurement')
    if not timeouts:
        return result
    result['ppa_status'] = 'physical_timeout_retained_results' if measurement else 'physical_timeout_no_results'
    if not measurement:
        if set(timeouts) != set(SEEDS):
            raise ValueError('completed physical seeds require their measurements')
        return result
    baseline = json.loads(native.BASELINES_PATH.read_text())
    reference = payload.get('ppa_reference')
    if (baseline.get('status') not in ('partial_1ghz_qualified', 'qualified_1ghz') or
            reference != baseline.get('tasks', {}).get(task) or
            reference.get('qualification_status') != 'qualified_1ghz' or
            not partial_provenance_valid(task, measurement, reference, records, source)):
        raise ValueError('invalid retained physical measurement provenance')
    if not result['full_functional_pass']:
        return result
    points = native.ppa_score(measurement, reference, rules['ppa_points'],
                              rules['ppa_reference_points'], rules['setup_violation_exponent'])
    time_points = max(0., min(rules['time_points'], rules['time_points'] *
                       (1-payload['elapsed_seconds']/payload['time_limit_seconds']))) if points > 0 else 0.
    bucket = min(round(rules['ppa_points']/rules['ppa_bucket_width']),
                 math.floor(points/rules['ppa_bucket_width']+.5)) if points > 0 else 0
    before = result['functional_total']+points+time_points
    result.update(ppa_eligible=True, ppa_score=points, time_score=time_points,
                  ppa_rank_bucket=bucket, display_score_before_candidate_penalty=before,
                  display_score=max(0., before-result['candidate_delivery_penalty']),
                  rank_key=[result['functional_total'], bucket, -payload['elapsed_seconds'] if points > 0 else 0])
    return result
