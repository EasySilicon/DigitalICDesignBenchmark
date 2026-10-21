"""One wall-clock budget per seed for every task's power-simulation build."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

LIMIT_SECONDS = 1200
POLICY_ID = 'power-compile-wall-1200s-v1'
TIMEOUT_STATUS = 'power_compile_timeout_zero'
TIMEOUT_EXIT_CODE = 124


class PowerCompileTimeout(TimeoutError):
    pass


def validate_records(records, source, task, *, require_complete=False):
    """Validate evaluator receipts once for live grading and archive replay."""
    if not isinstance(records, list):
        raise ValueError('power_compile_records must be a list')
    seeds = set()
    timed_out = False
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('power compile receipt must be an object')
        seed = record.get('layout_seed')
        elapsed = record.get('elapsed_seconds')
        if (type(seed) is not int or seed not in (11, 29, 47) or seed in seeds
                or record.get('policy_id') != POLICY_ID
                or record.get('limit_seconds') != LIMIT_SECONDS
                or record.get('task_id') != task or not source
                or record.get('candidate_source_sha256') != source
                or type(elapsed) not in (int, float)
                or not math.isfinite(elapsed) or elapsed < 0):
            raise ValueError('invalid/mismatched power compilation evidence')
        seeds.add(seed)
        if record.get('status') == 'timeout':
            validate_timeout(record, source, seed, task)
            timed_out = True
        elif record.get('status') != 'completed' or elapsed > LIMIT_SECONDS:
            raise ValueError('compile error or invalid completion is not a timeout zero')
    if require_complete and not timed_out and seeds != {11, 29, 47}:
        raise ValueError('new PPA score requires three completed power compile budget records')
    return timed_out


def apply_to_scored_record(record, *, require_complete=False):
    """Keep archive regrading from reviving an automatically zeroed PPA score.

    Unmarked historical records retain their original policy. Current records
    must retain source-bound receipts even when no PPA measurement exists.
    """
    measurement = record.get('ppa_measurement') or {}
    records = record.get('power_compile_records', measurement.get('power_compile_records', []))
    marked = (record.get('power_compile_policy') == POLICY_ID
              or measurement.get('power_compile_policy') == POLICY_ID
              or POLICY_ID in record.get('scoring_policy', '')
              or record.get('ppa_status') == TIMEOUT_STATUS)
    if not records and not marked and not require_complete:
        return dict(record)
    source = record.get('candidate_source_sha256') or record.get('candidate_sha256') or record.get('source_sha256') or measurement.get('source_sha256')
    if measurement and measurement.get('source_sha256') != source:
        raise ValueError('power compilation and PPA candidate source differ')
    timed_out = validate_records(records, source, record['task_id'],
                                 require_complete=require_complete or marked or bool(records))
    if record.get('ppa_status') == TIMEOUT_STATUS and not timed_out:
        raise ValueError('timeout zero requires a matching timeout receipt')
    result = dict(record, power_compile_policy=POLICY_ID, power_compile_records=records)
    if timed_out:
        before = result['functional_total']
        result.update(ppa_score=0, time_score=0, ppa_eligible=False,
                      ppa_rank_bucket=0, ppa_status=TIMEOUT_STATUS,
                      ppa_zero_reason='Power-simulation compilation exceeded the cumulative 1200-second per-seed wall-clock budget.',
                      display_score_before_candidate_penalty=before,
                      display_score=max(0.0, before-result.get('candidate_delivery_penalty', 0)))
    return result


def validate_timeout(record, source, seed, task='T10'):
    elapsed=record.get('elapsed_seconds')
    if (record.get('policy_id') != POLICY_ID or record.get('limit_seconds') != LIMIT_SECONDS
            or record.get('status') != 'timeout' or type(elapsed) not in (int,float)
            or not math.isfinite(elapsed) or elapsed < LIMIT_SECONDS
            or record.get('task_id') != task or record.get('candidate_source_sha256') != source or record.get('layout_seed') != seed
            or record.get('process_group_terminated') is not True):
        raise ValueError('missing source-bound 1200-second power compile timeout evidence')


def stop_group(process):
    """The compiler/make and its children share our newly created session."""
    try:os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:pass
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:pass
    # A parent may exit before a compiler grandchild; always clean the group.
    try:os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:pass
    process.wait()


class CompileBudget:
    def __init__(self, output, source, seed, *, task='T10', seconds=LIMIT_SECONDS):
        if not math.isfinite(seconds) or seconds<=0:raise ValueError('invalid compile budget')
        self.output=Path(output);self.seconds=seconds
        self.record=dict(policy_id=POLICY_ID,limit_seconds=seconds,task_id=task,
            candidate_source_sha256=source,layout_seed=seed,commands=[])

    def __enter__(self):
        self.output.mkdir(parents=True,exist_ok=True)
        if (self.output/'power_compile.json').exists():
            raise ValueError('compile attempt already recorded; preserve it before an explicit retry')
        self.started=time.monotonic()
        self.record['started_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
        return self

    def expired(self):
        self.record['process_group_terminated']=True
        raise PowerCompileTimeout('Power-simulation compilation exceeded 1200 seconds')

    def run(self, command, log, cwd, **launch_options):
        command_started=time.monotonic()
        remaining=self.seconds-(time.monotonic()-self.started)
        if remaining<=0:self.expired()
        entry=dict(command=list(map(str,command)),log=str(log));self.record['commands'].append(entry)
        print('RUN',log,flush=True)
        with Path(log).open('w') as stream:
            process=subprocess.Popen(command,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,
                start_new_session=True,**launch_options)
            entry['process_group']=process.pid
            try:
                remaining=self.seconds-(time.monotonic()-self.started)
                if remaining<=0:
                    stop_group(process);self.expired()
                code=process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                stop_group(process);entry['returncode']=process.returncode
                self.expired()
            except BaseException:
                stop_group(process)
                raise
            entry['returncode']=code
            if code:raise subprocess.CalledProcessError(code,command)
        if time.monotonic()-self.started>self.seconds:self.expired()
        return time.monotonic()-command_started

    def __exit__(self, kind, error, traceback):
        elapsed=time.monotonic()-self.started
        timeout=isinstance(error,PowerCompileTimeout) or (kind is None and elapsed>self.seconds)
        self.record.update(status='timeout' if timeout else 'completed' if kind is None else 'error',
            elapsed_seconds=elapsed,ended_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        if timeout:self.record.update(process_group_terminated=True,ppa_score=0,time_score=0)
        for entry in self.record['commands']:
            path=Path(entry['log'])
            if path.is_file():
                payload=path.read_bytes()
                entry['log_artifact']=dict(path=str(path),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
        (self.output/'power_compile.json').write_text(json.dumps(self.record,indent=2)+'\n')
        if timeout and kind is None:raise PowerCompileTimeout('Power-simulation compilation exceeded 1200 seconds')
        return False
