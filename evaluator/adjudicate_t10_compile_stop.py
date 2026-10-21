#!/usr/bin/env python3
"""Record the user's explicit stop/zero decision, never infer a timeout rule."""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from run_t10_candidate_40g import POLICY, assert_serial, properties, sample, save
from t10_candidate_physical import artifact, prepare

STATUS = 'user_adjudicated_compile_stop_zero'
DECISION = '那就应该判它0分'


def validate_decision(receipt, runtime, model, source):
    if (receipt.get('kind') != STATUS or receipt.get('user_decision') != DECISION
            or receipt.get('model') != model or model != 'gpt-6-sol'
            or receipt.get('candidate_source_sha256') != source
            or receipt.get('resource_policy') != POLICY
            or receipt.get('ppa_score') != 0 or receipt.get('time_score') != 0
            or receipt.get('measurement_completed') is not False):
        raise ValueError('missing explicit, source-bound user stop decision')
    if (runtime.get('policy') != POLICY or runtime.get('confirmed') is not True
            or not runtime.get('ended_utc') or runtime.get('exit_code') in (None, 0)
            or runtime.get('systemd_result') == 'oom-kill'):
        raise ValueError('user-stopped compiler must be terminal; do not relabel an OOM')
    if runtime.get('unit', '').removesuffix('.scope') != receipt['unit'].removesuffix('.scope'):
        raise ValueError('stopped runtime unit differs from the authorized target')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--trials-root', type=Path, required=True)
    parser.add_argument('--expected-pid', type=int, required=True)
    parser.add_argument('--user-decision', required=True)
    args = parser.parse_args()
    if args.user_decision != DECISION:
        raise ValueError('this one-off adjudication requires the explicit user decision')
    work = args.work.resolve(); model = 'gpt-6-sol'; seed = 11
    state_path = work/'t10_ppa_scores40.json'
    state = json.loads(state_path.read_text()); row = state['models'][model]
    if (state['policy'] != POLICY or row['status'] != 'activity_power_running'
            or row['ppa_score'] is not None or row['layout_seed'] != seed):
        raise ValueError('target is not the currently unscored seed-11 power evaluation')
    item = prepare(model, args.trials_root.resolve(), work)
    directory = work/model/f'seed{seed}'; runtime_path = directory/'activity_runtime40.json'
    runtime = json.loads(runtime_path.read_text())
    unit = runtime['unit'].removesuffix('.scope') + '.scope'
    if unit != 't10-40-power-gpt-6-sol-s11-area1-front0.scope':
        raise ValueError('unexpected target scope')
    props = properties(unit)
    if props.get('ActiveState') != 'active':raise ValueError('target is no longer active; inspect before adjudicating')
    assert_serial(unit)
    group = Path('/sys/fs/cgroup')/props['ControlGroup'].lstrip('/')
    if str(args.expected_pid) not in (group/'cgroup.procs').read_text().split():
        raise ValueError('expected compiler is outside the target scope')
    argv = Path(f'/proc/{args.expected_pid}/cmdline').read_bytes().decode().split('\0')
    flags = work/model/'activity_seed11/build/Vnpu_systolic_matmul_16x16__hierMkArgs.f'
    if Path(argv[0]).name != 'verilator_bin' or argv[1:3] != ['-f', str(flags)]:
        raise ValueError('expected process is not this candidate parent compiler')
    ticks = Path(f'/proc/{args.expected_pid}/stat').read_text().split()
    wall = float(Path('/proc/uptime').read_text().split()[0])-int(ticks[21])/os.sysconf('SC_CLK_TCK')
    out = work/model/'user_compile_stop40'; out.mkdir()
    for path in (state_path, runtime_path, directory/'activity40.log', flags):
        shutil.copy2(path, out/path.name)
    request = dict(kind=STATUS, model=model, layout_seed=seed, user_decision=DECISION,
        candidate_source_sha256=item['source_sha256'], resource_policy=POLICY,
        ppa_score=0, time_score=0, measurement_completed=False, unit=unit,
        compiler_pid=args.expected_pid, compiler_start_ticks=ticks[21],
        observed_compiler_wall_seconds=wall,
        requested_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        resources=sample(props['ControlGroup']), memory_events=(group/'memory.events').read_text(),
        reason='User explicitly adjudicated zero after excessive compiler runtime; not OOM and not a suite-wide automatic timeout.',
        preserved_inputs={p.name:artifact(p) for p in out.iterdir()})
    save(out/'request.json', request)
    subprocess.run(['systemctl','--user','kill','--kill-whom=all','--signal=SIGTERM',unit],check=True)
    # Only the exact validated candidate scope is stopped. The coordinator
    # writes its terminal runtime and releases its lock without running seed 29.
    with (work/'serial40.lock').open('a') as lock:
        deadline=time.monotonic()+45
        while True:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>deadline:raise RuntimeError('coordinator has not released its lock; no score changed')
                time.sleep(1)
        assert_serial()
        runtime=json.loads(runtime_path.read_text())
        validate_decision(request,runtime,model,item['source_sha256'])
        state=json.loads(state_path.read_text());shutil.copy2(state_path,out/'queue_after_stop.json')
        receipt=dict(request, request=artifact(out/'request.json'), terminal_runtime=artifact(runtime_path),
            queue_after_stop=artifact(out/'queue_after_stop.json'))
        save(out/'decision.json',receipt)
        row=state['models'][model]
        if row['ppa_score'] is not None:raise ValueError('coordinator produced a score; refuse overwrite')
        row.update(status=STATUS,ppa_score=0,time_score=0,display_score=50,failing_seed=seed,
            adjudication=artifact(out/'decision.json'))
        state['status']='complete' if all(r['ppa_score'] is not None for r in state['models'].values()) else 'pending_infrastructure_review'
        save(state_path,state)
    print('USER-ADJUDICATED',model,'PPA=0 time=0 functional=50; original artifacts preserved at',out)


if __name__=='__main__':main()
