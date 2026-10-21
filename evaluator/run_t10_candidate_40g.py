#!/usr/bin/env python3
"""User-authorized serial 40-GiB retry, with swap and unlimited VA.

Preserves the original 32-GiB attempts. Confirmed OOM at the new limit is an
adjudicated PPA zero; infrastructure failures still require investigation.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time
import traceback

from t10_candidate_physical import REPO, TRIALS, prepare, run_seed, sha, artifact, write_new_or_same
from grade_t10_candidate_ppa import grade

POLICY=dict(memory_max_bytes=40*1024**3,memory_swap_max='max',max_address_space='unlimited',
            concurrency=1,cpu_threads=4,user_authorized_oom_ppa_zero=True,
            note='40 GiB diagnostic remeasurement, not a claim of 32 GiB compliance')


def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');temp.replace(path)


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


def monitor(unit,record_path,process=None):
    runtime=dict(policy=POLICY,unit=unit,started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),samples=0,
                 peak_memory_bytes=0,peak_swap_bytes=0,confirmed=False)
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
        time.sleep(2)
    runtime.update(ended_utc=dt.datetime.now(dt.timezone.utc).isoformat(),systemd_result=properties(unit).get('Result','unloaded'))
    if process is not None:runtime['exit_code']=process.wait()
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


def physical(item,seed,work,orfs,adopt=None):
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
        runtime=monitor(unit,directory/'runtime40.json')
    else:
        assert_serial()
        unit=next(arg.split('=',1)[1] for arg in command if arg.startswith('--unit='))
        with (directory/'baseline40.log').open('x') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=os.environ|{'MALLOC_ARENA_MAX':'2'})
            runtime=monitor(unit,directory/'runtime40.json',process)
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


def preserve_python_entry_failure(model_dir):
    """Explicitly retry our diagnosed launcher bug, retaining its entire attempt."""
    seed=model_dir/'seed11';activity=model_dir/'activity_seed11'
    archive=seed/'power_python_entry_failure_preserved'
    if archive.exists():raise ValueError('launcher-error retry already prepared; inspect instead of retrying again')
    runtime=json.loads((seed/'activity_runtime40.json').read_text())
    log=(activity/'connectivity.log').read_text()
    if (activity/'power.json').exists() or runtime.get('exit_code')!=1 or \
            "ModuleNotFoundError: No module named 'odb'" not in log:
        raise ValueError('not the diagnosed Python-entry failure; refusing to retry')
    archive.mkdir()
    for name in ('activity40.log','activity_runtime40.json'):
        (seed/name).rename(archive/name)
    activity.rename(archive/'activity_seed11')
    save(archive/'repair.json',dict(reason='system Python used instead of OpenROAD -python',
        corrected_helper=artifact(REPO/'evaluator/t10_candidate_power.py'),
        utc=dt.datetime.now(dt.timezone.utc).isoformat(),physical_outputs_unchanged=True))


def preserve_shell_target_failure(model_dir):
    seed=model_dir/'seed11';activity=model_dir/'activity_seed11'
    archive=seed/'power_shell_target_failure_preserved'
    if archive.exists():raise ValueError('shell-target repair already prepared')
    log=(activity/'shell_synth.log').read_text()
    runtime=json.loads((seed/'activity_runtime40.json').read_text())
    if (activity/'power.json').exists() or runtime.get('exit_code')!=1 or \
            '[ERROR ORD-2013]' not in log or 'LEF master' not in log:
        raise ValueError('not the diagnosed shell-target failure')
    archive.mkdir()
    for name in ('activity40.log','activity_runtime40.json'):(seed/name).rename(archive/name)
    for name in ('shell_synth.log','shell.mk','connectivity.log','connectivity.json'):
        shutil.copy2(activity/name,archive/name)
    save(archive/'repair.json',dict(reason='request mapped shell Verilog only, not aggregate synth/ODB target',
        corrected_helper=artifact(REPO/'evaluator/t10_candidate_power.py'),
        utc=dt.datetime.now(dt.timezone.utc).isoformat(),physical_outputs_unchanged=True,
        successful_connectivity_reused=True))


def preserve_peripheral_speed_attempt(model_dir):
    """An operator-ended, unmeasured-shell optimization is not a candidate zero."""
    seed=model_dir/'seed11';activity=model_dir/'activity_seed11'
    archive=seed/'peripheral_speed_mapping_preserved'
    if (activity/'power.json').exists():raise ValueError('cannot replace a completed power measurement')
    if archive.exists():raise ValueError('peripheral speed attempt already archived')
    if not (seed/'activity40.log').exists():return
    archive.mkdir()
    for name in ('activity40.log','activity_runtime40.json'):
        if (seed/name).exists():(seed/name).rename(archive/name)
    for name in ('shell_synth.log','shell.mk','connectivity.log','connectivity.json'):
        if (activity/name).exists():shutil.copy2(activity/name,archive/name)
    save(archive/'transition.json',dict(reason='unmeasured periphery switched from timing-first to area-first mapping',
        adjudication='evaluator infrastructure reconfiguration; not a candidate failure',
        same_seed_routed_pe_unchanged=True,full_gate_workload_unchanged=True,
        utc=dt.datetime.now(dt.timezone.utc).isoformat()))


def preserve_peripheral_frontend_attempt(model_dir):
    """Preserve an explicitly canceled frontend, not a failed candidate.

    Keep the mapped shell/configuration and connectivity in place so the
    completed synthesis is reused. Only temporary simulation builds move.
    """
    seed=model_dir/'seed11';activity=model_dir/'activity_seed11'
    archive=seed/'peripheral_frontend_O1_preserved'
    if archive.exists():raise ValueError('frontend transition already preserved')
    intent=model_dir/'frontend_transition_requested.json'
    request=json.loads(intent.read_text())
    runtime=json.loads((seed/'activity_runtime40.json').read_text())
    inputs=json.loads((seed/'inputs40.json').read_text())
    args=activity/'build/Vnpu_systolic_matmul_16x16__hierMkArgs.f'
    if (activity/'power.json').exists() or request.get('to')!='O0_unmeasured_parent' or \
            request.get('resource_policy')!=POLICY or request.get('source_sha256')!=inputs['source_sha256'] or \
            runtime.get('exit_code') in (None,0) or runtime.get('systemd_result')=='oom-kill' or \
            runtime.get('confirmed') is not True or runtime.get('policy')!=POLICY or \
            '-O0' in args.read_text().split():
        raise ValueError('not an explicitly canceled default-optimization frontend')
    if artifact(Path(request['mapped_shell']['path']))!=request['mapped_shell'] or \
            sha(args)!=request['parent_arguments_sha256']:
        raise ValueError('preserved frontend inputs changed')
    for name in ('build','planning_only','actual_modules'):
        path=activity/name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError('unexpected frontend staging path')
    archive.mkdir()
    shutil.copy2(intent,archive/intent.name)
    for name in ('activity40.log','activity_runtime40.json'):(seed/name).rename(archive/name)
    for path in activity.glob('*.log'):shutil.copy2(path,archive/path.name)
    for name in ('shell_area.mk','connectivity.json'):
        if (activity/name).exists():shutil.copy2(activity/name,archive/name)
    for name in ('build','planning_only','actual_modules'):
        path=activity/name
        if path.exists():path.rename(archive/name)
    save(archive/'transition.json',dict(
        reason='disable expensive simulator optimization of the unmeasured large parent',
        adjudication='intentional evaluator frontend reconfiguration; not a candidate failure',
        mapped_shell=request['mapped_shell'],physical_outputs_unchanged=True,
        completed_synthesis_unchanged=True,full_gate_workload_unchanged=True,
        utc=dt.datetime.now(dt.timezone.utc).isoformat()))


def validate_frontend_retry(state,model):
    row=state['models'][model]
    if state['status']!='pending_infrastructure_review' or row['status']!='pending_infrastructure_review' or \
            row['ppa_score'] is not None or row.get('layout_seed')!=11 or \
            any(state['models'][other]['ppa_score'] is None for other in TRIALS if other!=model):
        raise ValueError('frontend retry must target only the canceled, unscored candidate')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--trials-root',type=Path,required=True)
    p.add_argument('--orfs',type=Path,required=True);p.add_argument('--adopt-pid',type=int);p.add_argument('--adopt-unit')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--adopt-model',choices=TRIALS,default='gpt-6.1-sol')
    p.add_argument('--adopt-seed',type=int,choices=(11,29,47),default=11)
    p.add_argument('--retry-python-entry-failure',choices=TRIALS)
    p.add_argument('--controller-unit')
    p.add_argument('--retry-shell-target-failure',choices=TRIALS,nargs='+',default=[])
    p.add_argument('--resume-idle-power',action='store_true',
        help='explicit idle-queue handoff after all physical seeds have completed')
    p.add_argument('--peripheral-area-transition',action='store_true')
    p.add_argument('--retry-peripheral-frontend',choices=TRIALS)
    a=p.parse_args();work=a.work.resolve();orfs=a.orfs.resolve()
    if a.retry_peripheral_frontend and not (a.resume and a.resume_idle_power):
        raise ValueError('frontend retry requires an explicit idle queue handoff')
    resource.setrlimit(resource.RLIMIT_AS,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))
    with (work/'serial40.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        output=work/'t10_ppa_scores40.json'
        if a.resume:
            state=json.loads(output.read_text())
            if a.retry_peripheral_frontend:
                if state['policy']!=POLICY:raise ValueError('resource policy changed')
                assert_serial();validate_frontend_retry(state,a.retry_peripheral_frontend)
                preserve_peripheral_frontend_attempt(work/a.retry_peripheral_frontend)
                row=state['models'][a.retry_peripheral_frontend]
                row.update(status='queued_after_frontend_adjustment',
                    previous_frontend_diagnostic=row.pop('diagnostic',''))
                state.update(status='running_serial_40g',
                    peripheral_frontend_policy='-O0 for >=128 MiB unmeasured parent; same-seed PE unchanged')
            if state['policy']!=POLICY or state['status']!='running_serial_40g':raise ValueError('queue is not safely resumable')
            if a.resume_idle_power:
                if a.adopt_pid:raise ValueError('idle resume cannot adopt a live task')
                assert_serial()
                for model in TRIALS:
                    if state['models'][model]['ppa_score'] is None:
                        for seed in (11,29,47):
                            if not completed_physical(work/model/f'seed{seed}'):
                                raise ValueError('idle power resume requires all physical outputs')
            else:
                current=state['models'][a.adopt_model]
                if not a.adopt_pid or current['status']!='physical_running' or current['layout_seed']!=a.adopt_seed:
                    raise ValueError('resume must attach the exact running physical attempt')
            state.setdefault('monitor_handoffs',[]).append(dict(previous_runner_sha256=state['runner_sha256'],
                utc=dt.datetime.now(dt.timezone.utc).isoformat(),model=a.retry_peripheral_frontend or a.adopt_model,seed=a.adopt_seed))
            state['runner_sha256']=sha(Path(__file__))
        else:
            if output.exists():raise ValueError('40 GiB queue already exists; inspect it instead of restarting')
            state=dict(status='running_serial_40g',policy=POLICY,models={},runner_sha256=sha(Path(__file__)))
            for model in ('kimi-k3','deepseek-flash','glm-5.3-flash'):
                old=json.loads((REPO/f'results/{model}/T10.json').read_text())
                if old.get('ppa_score')!=0:raise ValueError('existing non-GPT zero changed')
                state['models'][model]=dict(status='existing_gate_zero',ppa_score=0)
            for model in TRIALS:state['models'][model]=dict(status='queued',ppa_score=None)
        if a.controller_unit:state['controller_unit']=a.controller_unit
        save(output,state)
        order=['gpt-6.1-sol','gpt-6-astra','gpt-6-sol']
        # Attach a live native producer before attempting any other EDA work.
        if a.resume and not a.resume_idle_power:order.remove(a.adopt_model);order.insert(0,a.adopt_model)
        if a.peripheral_area_transition:
            if not a.resume_idle_power:raise ValueError('mapping transition requires an idle power resume')
            for model in TRIALS:
                preserve_peripheral_speed_attempt(work/model)
                if state['models'][model]['ppa_score'] is None:
                    state['models'][model]['status']='queued_peripheral_area_mapping'
            state['peripheral_mapping_policy']='ABC_AREA=1 for unmeasured shell only; routed PEs unchanged'
            save(output,state)
        if a.retry_python_entry_failure:
            if not a.resume:raise ValueError('diagnosed retry requires an explicit queue resume')
            retry=state['models'][a.retry_python_entry_failure]
            if retry['status']!='pending_infrastructure_review':raise ValueError('model is not awaiting infrastructure repair')
            preserve_python_entry_failure(work/a.retry_python_entry_failure)
            retry.update(status='queued_after_launcher_repair',previous_diagnostic=retry.pop('diagnostic'))
            save(output,state)
        for model in a.retry_shell_target_failure:
            if not a.resume:raise ValueError('diagnosed retry requires an explicit queue resume')
            retry=state['models'][model]
            if retry['status']!='pending_infrastructure_review':raise ValueError('model is not awaiting shell repair')
            preserve_shell_target_failure(work/model)
            retry.update(status='queued_after_shell_target_repair',shell_failure_diagnostic=retry.pop('diagnostic'))
            save(output,state)
        for model in order:
            row=state['models'][model]
            if row['ppa_score'] is not None:continue
            try:
                item=prepare(model,a.trials_root.resolve(),work)
                for seed in (11,29,47):
                    if a.resume and completed_physical(work/model/f'seed{seed}'):continue
                    row.update(status='physical_running',layout_seed=seed);save(output,state)
                    adopt=(a.adopt_pid,a.adopt_unit) if model==a.adopt_model and seed==a.adopt_seed and a.adopt_pid else None
                    record,runtime=physical(item,seed,work,orfs,adopt)
                    if record['exit_code']:
                        if runtime['confirmed'] and runtime['systemd_result']=='oom-kill':
                            row.update(status='user_adjudicated_40g_oom_zero',ppa_score=0,time_score=0,
                                failing_seed=seed,evidence=artifact(work/model/f'seed{seed}/baseline40.json'))
                            print('USER-ADJUDICATED ZERO',model,seed,flush=True)
                            break
                        raise RuntimeError('40 GiB flow failed without confirmed OOM; review infrastructure before scoring')
                if row['ppa_score']==0:save(output,state);continue
                for seed in (11,29,47):
                    row.update(status='activity_power_running',layout_seed=seed);save(output,state)
                    assert_serial()
                    unit=f't10-40-power-{model.replace(".","_")}-s{seed}-area1'+('-front0' if a.retry_peripheral_frontend else '')
                    cmd=['systemd-run','--user','--scope',f'--unit={unit}','-p','MemoryMax=40G','-p','MemorySwapMax=infinity',
                        '-p','CPUQuota=400%','python3','-u',str(REPO/'evaluator/t10_candidate_power.py'),
                        '--model-dir',str(work/model),'--seed',str(seed),'--orfs',str(orfs)]
                    with (work/model/f'seed{seed}/activity40.log').open('x') as log:
                        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
                        runtime=monitor(unit,work/model/f'seed{seed}/activity_runtime40.json',child)
                    if runtime['exit_code']:
                        if runtime['confirmed'] and runtime['systemd_result']=='oom-kill':
                            row.update(status='user_adjudicated_40g_power_oom_zero',ppa_score=0,time_score=0,failing_seed=seed)
                            break
                        raise RuntimeError('activity/power failed; preserve logs and review before scoring')
                if row['ppa_score']==0:save(output,state);continue
                report=grade(model,work,a.trials_root.resolve(),orfs)
                report_path=work/model/'scored40.json';write_new_or_same(report_path,json.dumps(report,indent=2)+'\n')
                row.update(status='measured_and_scored_40g',ppa_score=report['score']['ppa_score'],
                    time_score=report['score']['time_score'],display_score=report['score']['display_score'],report=artifact(report_path))
            except Exception:
                row.update(status='pending_infrastructure_review',diagnostic=traceback.format_exc())
                print('PENDING',model,row['diagnostic'],flush=True)
            save(output,state)
        state['status']='complete' if all(row['ppa_score'] is not None for row in state['models'].values()) else 'pending_infrastructure_review'
        save(output,state)


if __name__=='__main__':main()
