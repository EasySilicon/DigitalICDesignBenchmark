#!/usr/bin/env python3
"""Monitor serial T10 physical work under the 40-GiB resource policy.

Preserve source-bound receipts, completed outputs and earlier attempts. Physical
and power compilation deadlines are enforced by their shared budget modules.
"""
import datetime as dt
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from physical_budget import T10_LIMIT_SECONDS as PHYSICAL_SECONDS, receipt as physical_receipt, stop_scope, timed_out as physical_timed_out

from t10_candidate_physical import REPO, run_seed, sha, artifact, write_new_or_same, prepare, trial_paths
from power_compile_budget import TIMEOUT_EXIT_CODE, TIMEOUT_STATUS, validate_timeout

POLICY=dict(memory_max_bytes=40*1024**3,memory_swap_max='max',max_address_space='unlimited',
            concurrency=1,cpu_threads=4,user_authorized_oom_ppa_zero=True,
            note='40 GiB diagnostic remeasurement, not a claim of 32 GiB compliance')


def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');temp.replace(path)


def compile_timeout_zero(work,model,seed,runtime,source):
    if runtime.get('exit_code')!=TIMEOUT_EXIT_CODE:return None
    if not runtime.get('confirmed') or runtime.get('policy')!=POLICY or runtime.get('systemd_result')=='oom-kill':
        raise ValueError('compile timeout lacks confirmed runtime policy')
    path=work/model/f'activity_seed{seed}/power_compile.json'
    validate_timeout(json.loads(path.read_text()),source,seed)
    return dict(status=TIMEOUT_STATUS,ppa_score=0,time_score=0,display_score=50,
        failing_seed=seed,evidence=artifact(path))


def properties(unit):
    if not unit.endswith('.scope'):unit+='.scope'
    result=subprocess.run(['systemctl','--user','show',unit,'-p','ActiveState','-p','Result','-p','ControlGroup',
        '-p','MemoryPeak','-p','MemorySwapPeak'],text=True,capture_output=True,check=False)
    values=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode and not values:return dict(ActiveState='inactive',Result='unloaded')
    return values


def assert_serial(expected=None):
    units=subprocess.check_output(['systemctl','--user','list-units','--state=active','--type=scope','--plain','--no-legend'],text=True)
    names=[line.split()[0] for line in units.splitlines() if line.strip()]
    busy=[name for name in names if name.startswith(('ic_t10_candidate_','t10-power-','t10-40-power-')) and name!=expected]
    if busy:raise RuntimeError('another candidate EDA task is active; refusing parallel execution: '+str(busy))


def wait_scope_inactive(unit,timeout=300):
    """Wait for systemd to retire a finished scope before admitting the next seed."""
    deadline=time.monotonic()+timeout
    while properties(unit).get('ActiveState') in ('active','activating','deactivating'):
        if time.monotonic() >= deadline:
            raise RuntimeError(f'EDA scope did not become inactive after {timeout}s: {unit}')
        time.sleep(.2)


def recover_retired_timeout(directory,*,model,source,seed,elapsed_seconds,ended_utc):
    """Finish evidence writing after monitor cleanup failed but the scope later retired."""
    directory=Path(directory);runtime_path=directory/'runtime40.json'
    budget_path=directory/'physical_budget.json';marker=directory/'baseline40.json'
    if budget_path.exists() or marker.exists():
        raise ValueError('terminal evidence already exists; refusing recovery overwrite')
    runtime=json.loads(runtime_path.read_text())
    if (runtime.get('policy')!=POLICY or not runtime.get('confirmed') or
            runtime.get('unit') is None or properties(runtime['unit']).get('ActiveState') in
            ('active','activating','deactivating')):
        raise ValueError('timeout recovery requires a confirmed retired monitored scope')
    if elapsed_seconds < PHYSICAL_SECONDS:
        raise ValueError('timeout recovery elapsed time is below the standard deadline')
    inputs_path=directory/'inputs40.json';inputs=json.loads(inputs_path.read_text())
    if inputs.get('model')!=model or inputs.get('source_sha256')!=source or inputs.get('layout_seed')!=seed:
        raise ValueError('timeout recovery identity changed')
    runtime.update(ended_utc=ended_utc,systemd_result='success',exit_code=124,
                   physical_timeout=True,terminal_record_recovered_after_scope_retirement=True)
    save(runtime_path,runtime)
    save(budget_path,physical_receipt('T10',source,seed,elapsed_seconds,'timeout',
        started_utc=runtime['started_utc'],ended_utc=ended_utc,process_group_terminated=True,
        terminal_record_recovered_after_scope_retirement=True))
    record=dict(status='failed_40g_requires_adjudication',model=model,layout_seed=seed,exit_code=124,
        inputs_sha256=sha(inputs_path),artifacts={},resource_policy=POLICY,runtime=artifact(runtime_path),
        terminal_record_recovered_after_scope_retirement=True)
    save(marker,record)
    return record


def sample(cgroup):
    root=Path('/sys/fs/cgroup')/cgroup.lstrip('/')
    row={name:(root/name).read_text().strip() for name in
         ('memory.max','memory.swap.max','memory.current','memory.peak','memory.swap.current')}
    if (root/'memory.swap.peak').exists():row['memory.swap.peak']=(root/'memory.swap.peak').read_text().strip()
    if row['memory.max']!=str(POLICY['memory_max_bytes']) or row['memory.swap.max']!='max':
        raise ValueError('actual cgroup does not match the authorized 40 GiB + swap policy')
    for raw in (root/'cgroup.procs').read_text().split():
        try:limits=(Path('/proc')/raw/'limits').read_text()
        except FileNotFoundError:continue
        line=next(line for line in limits.splitlines() if line.startswith('Max address space'))
        if line.split()[3:5]!=['unlimited','unlimited']:raise ValueError('VA limit remains active: '+line)
    return row


def monitor(unit,record_path,process=None,*,physical_identity=None,physical_started_utc=None,
            physical_elapsed_seconds=None,physical_limit_seconds=None,
            limit_authorization=None):
    if physical_limit_seconds is None and not limit_authorization:
        physical_limit_seconds=PHYSICAL_SECONDS
    if physical_limit_seconds != PHYSICAL_SECONDS and not limit_authorization:
        raise ValueError('a nonstandard physical deadline requires an explicit authorization record')
    already_elapsed=(max(0.,physical_elapsed_seconds) if physical_elapsed_seconds is not None else
        max(0.,(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(physical_started_utc)).total_seconds())
        if physical_started_utc else 0.)
    physical_started=time.monotonic()-already_elapsed
    physical_timeout=False
    runtime=dict(policy=POLICY,unit=unit,started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),samples=0,
                 peak_memory_bytes=0,peak_swap_bytes=0,confirmed=False)
    if physical_started_utc:runtime['started_utc']=physical_started_utc
    while True:
        props=properties(unit);cgroup=props.get('ControlGroup')
        if cgroup:
            try:
                values=sample(cgroup);runtime.update(confirmed=True,control_group=cgroup,last_sample=values)
                runtime['samples']+=1
                runtime['peak_memory_bytes']=max(runtime['peak_memory_bytes'],int(values['memory.peak']))
                runtime['peak_swap_bytes']=max(runtime['peak_swap_bytes'],int(values.get('memory.swap.peak',values['memory.swap.current'])))
            except FileNotFoundError:pass
        save(record_path,runtime)
        if process is not None:
            if process.poll() is not None:break
        elif props.get('ActiveState') not in ('active','activating'):break
        if (physical_identity is not None and physical_limit_seconds is not None and
                time.monotonic()-physical_started >= physical_limit_seconds):
            stop_scope(unit)
            if process is not None:
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            physical_timeout=True
            break
        time.sleep(2)
    # systemd may keep a stopped scope visible as active for a short interval
    # after the producer has exited.  Retire it before the next serial seed is
    # admitted, otherwise assert_serial() can reject a non-overlapping run.
    wait_scope_inactive(unit)
    runtime.update(ended_utc=dt.datetime.now(dt.timezone.utc).isoformat(),systemd_result=properties(unit).get('Result','unloaded'))
    if process is not None:runtime['exit_code']=process.wait()
    if physical_identity is not None:
        task,source,seed=physical_identity
        elapsed=time.monotonic()-physical_started
        physical_timeout=physical_timeout or (physical_limit_seconds is not None and
                                               elapsed > physical_limit_seconds)
        status='timeout' if physical_timeout else 'completed' if runtime.get('exit_code',0)==0 else 'error'
        receipt=physical_receipt(task,source,seed,elapsed,status,
             started_utc=runtime['started_utc'],ended_utc=runtime['ended_utc'],
             process_group_terminated=physical_timeout)
        if physical_limit_seconds != PHYSICAL_SECONDS:
            receipt.update(policy_id=('physical-completion-continuation-v1' if physical_limit_seconds is None
                                      else 'physical-wall-authorized-exception-v1'),
                base_policy_id=receipt['policy_id'],limit_seconds=physical_limit_seconds,
                limit_authorization=limit_authorization)
        save(record_path.parent/'physical_budget.json',receipt)
        if physical_timeout:runtime.update(exit_code=124,physical_timeout=True)
    save(record_path,runtime)
    return runtime


def archive32(directory,orfs):
    archive=directory/'attempt32_preserved'
    if archive.exists():return
    archive.mkdir()
    for name in ('inputs.json','baseline.json','baseline.log','synth.json','synth.log'):
        if (directory/name).exists():shutil.copy2(directory/name,archive/name)
    original=directory/'inputs.json'
    if original.exists():
        d=json.loads(original.read_text())
        for kind in ('logs','reports'):
            source=orfs/'flow'/kind/'asap7'/d['pe_module']/d['variant']
            if source.exists():shutil.copytree(source,archive/kind)


def physical(item,seed,work,orfs,adopt=None,*,physical_limit_seconds=None,
             limit_authorization=None,physical_started_utc=None,physical_elapsed_seconds=None):
    if physical_limit_seconds is None and not limit_authorization:
        physical_limit_seconds=PHYSICAL_SECONDS
    directory=work/item['model']/f'seed{seed}';directory.mkdir(exist_ok=True,parents=True)
    archive32(directory,orfs)
    marker=directory/'baseline40.json'
    if marker.exists():raise ValueError('40 GiB attempt already has a terminal result; do not retry silently')
    prepared=run_seed(item,seed,work,orfs,'baseline',memory_gib=40,allow_swap=True,prepare_only=True)
    write_new_or_same(directory/'active_attempt.json',json.dumps(dict(inputs='inputs40.json',physical='baseline40.json'),indent=2)+'\n')
    inputs=prepared['inputs'];command=prepared['command'];process=None
    if adopt:
        pid,unit=adopt
        cmdline=Path(f'/proc/{pid}/cmdline').read_bytes().decode()
        if inputs['variant'] not in cmdline:raise ValueError('adopted producer identity changed')
        assert_serial(unit)
        transition=dict(native_producer_pid=pid,process_start_ticks=Path(f'/proc/{pid}/stat').read_text().split()[21],
            new_inputs=artifact(Path(prepared['input_path'])),policy=POLICY,
            note='monitor attached to existing native producer; no physical stages restarted')
        if (directory/'inputs.json').exists():transition['original_inputs']=artifact(directory/'inputs.json')
        transition_path=directory/('monitor_handoff40.json' if (directory/'runtime40.json').exists() else 'transition40.json')
        write_new_or_same(transition_path,json.dumps(transition,indent=2)+'\n')
        prior=json.loads((directory/'runtime40.json').read_text()) if (directory/'runtime40.json').exists() else {}
        runtime=monitor(unit,directory/'runtime40.json',physical_identity=('T10',item['source_sha256'],seed),
                        physical_started_utc=prior.get('started_utc'),physical_limit_seconds=physical_limit_seconds,
                        limit_authorization=limit_authorization)
    else:
        assert_serial()
        unit=next(arg.split('=',1)[1] for arg in command if arg.startswith('--unit='))
        with (directory/'baseline40.log').open('x') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=os.environ|{'MALLOC_ARENA_MAX':'2'})
            runtime=monitor(unit,directory/'runtime40.json',process,physical_identity=('T10',item['source_sha256'],seed),
                            physical_started_utc=physical_started_utc,
                            physical_elapsed_seconds=physical_elapsed_seconds,
                            physical_limit_seconds=physical_limit_seconds,limit_authorization=limit_authorization)
    result_dir=orfs/'flow/results/asap7'/inputs['pe_module']/inputs['variant']
    paths=[result_dir/f'6_final.{ext}' for ext in ('odb','spef','sdc','v')]
    complete=all(path.is_file() for path in paths)
    rc=runtime.get('exit_code',0 if complete and runtime['systemd_result'] in ('success','unloaded') else 1)
    if rc==0 and not complete:rc=1
    record=dict(status='physical_flow_completed_not_qualified' if rc==0 else 'failed_40g_requires_adjudication',
        model=item['model'],layout_seed=seed,exit_code=rc,inputs_sha256=sha(Path(prepared['input_path'])),
        artifacts={path.name:artifact(path) for path in paths if path.exists()},resource_policy=POLICY,runtime=artifact(directory/'runtime40.json'))
    save(marker,record)
    return record,runtime


def completed_physical(directory):
    """Resume only verified successes; failures are never silently retried."""
    path=directory/'baseline40.json'
    if not path.exists():return False
    record=json.loads(path.read_text())
    if record['exit_code']!=0:raise ValueError('terminal physical failure requires review')
    if record.get('resource_policy')!=POLICY or record['inputs_sha256']!=sha(directory/'inputs40.json'):
        raise ValueError('completed physical policy or input binding changed')
    if set(record['artifacts'])!={'6_final.'+ext for ext in ('odb','spef','sdc','v')}:
        raise ValueError('incomplete final physical artifact set')
    for evidence in [*record['artifacts'].values(),record['runtime']]:
        if artifact(Path(evidence['path']))!=evidence:raise ValueError('completed evidence changed')
    runtime=json.loads(Path(record['runtime']['path']).read_text())
    if not runtime.get('confirmed'):raise ValueError('completed physical policy was never observed')
    return True


def run_candidates(trials,work,orfs):
    """Run explicit selections serially; never retry a terminal failed attempt."""
    from grade_t10_candidate_ppa import grade
    from t10_physical_with_slang import physical as current_physical
    output=work/'t10_ppa_scores40.json'
    selection={label:str(path) for label,path in trials.items()}
    if output.exists():
        state=json.loads(output.read_text())
        if state.get('policy')!=POLICY or state.get('trial_selection')!=selection:
            raise ValueError('resource policy or trial selection changed')
        if state['status']=='pending_infrastructure_review':
            raise ValueError('terminal failure requires review; automatic retry is disabled')
    else:
        state=dict(status='running_serial_40g',policy=POLICY,trial_selection=selection,
                   models={label:dict(status='queued',ppa_score=None) for label in trials})
    save(output,state)
    for model in trials:
        row=state['models'][model]
        if row['ppa_score'] is not None:continue
        try:
            item=prepare(model,trials,work)
            for seed in (11,29,47):
                directory=work/model/f'seed{seed}'
                if physical_timed_out(directory) or completed_physical(directory):continue
                row.update(status='physical_running',layout_seed=seed);save(output,state)
                record,runtime=current_physical(item,seed,work,orfs)
                if physical_timed_out(directory):continue
                if record['exit_code']:
                    if runtime.get('confirmed') and runtime.get('systemd_result')=='oom-kill':
                        row.update(status='resource_oom_zero',ppa_score=0,time_score=0,failing_seed=seed)
                        break
                    raise RuntimeError('physical flow failed; preserve evidence for attribution')
            if row['ppa_score']==0:save(output,state);continue
            for seed in (11,29,47):
                directory=work/model/f'seed{seed}'
                if physical_timed_out(directory) or (work/model/f'activity_seed{seed}/power.json').exists():continue
                row.update(status='activity_power_running',layout_seed=seed);save(output,state)
                assert_serial()
                unit=f't10-40-power-{model}-s{seed}'
                command=['systemd-run','--user','--scope',f'--unit={unit}',
                    '-p','MemoryMax=40G','-p','MemorySwapMax=infinity','-p','CPUQuota=400%',
                    sys.executable,'-u',str(REPO/'evaluator/t10_power_with_slang.py'),
                    '--model-dir',str(work/model),'--seed',str(seed),'--orfs',str(orfs)]
                with (directory/'activity40.log').open('x') as log:
                    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
                    runtime=monitor(unit,directory/'activity_runtime40.json',child)
                if runtime['exit_code']:
                    timeout=compile_timeout_zero(work,model,seed,runtime,item['source_sha256'])
                    if timeout:row.update(timeout);break
                    if runtime.get('confirmed') and runtime.get('systemd_result')=='oom-kill':
                        row.update(status='resource_power_oom_zero',ppa_score=0,time_score=0,failing_seed=seed)
                        break
                    raise RuntimeError('power flow failed; preserve evidence for attribution')
            if row['ppa_score']==0:save(output,state);continue
            report=grade(model,work,trials,orfs)
            report_path=work/model/'scored40.json'
            write_new_or_same(report_path,json.dumps(report,indent=2)+'\n')
            row.update(status='measured_and_scored_40g',ppa_score=report['score']['ppa_score'],
                       time_score=report['score']['time_score'],display_score=report['score']['display_score'],
                       report=artifact(report_path))
        except Exception as error:
            row.update(status='pending_infrastructure_review',diagnostic=str(error))
        save(output,state)
    state['status']='complete' if all(row['ppa_score'] is not None for row in state['models'].values()) else 'pending_infrastructure_review'
    save(output,state)
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial',action='append',required=True,metavar='LABEL=TRIAL_DIR')
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--orfs',type=Path,required=True)
    args=parser.parse_args();trials=trial_paths(args.trial);work=args.work.resolve()
    work.mkdir(parents=True,exist_ok=True)
    with (work/'serial40.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=run_candidates(trials,work,args.orfs.resolve())
    return 0 if state['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
