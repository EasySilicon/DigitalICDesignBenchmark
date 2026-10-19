"""Explicit, guarded PE infrastructure recovery from retained GRT.

Requires an actual terminal allocation failure and unchanged silicon inputs.
Keep the failed attempt; preserve the original input record; only change the
allocator/address-space envelope within the same 32 GiB RAM budget.
If that virtual-address limit still fails, --ram-cgroup is a separate explicit
correction to enforce actual memory with cgroup v2, not a larger RAM allowance.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from run_layout import BLOCKS, HERE, REPO, RTL, EXPECTED_RTL, baseline_files, run, sha, variant


def artifact(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,choices=(29,47),required=True)
    parser.add_argument('--orfs',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--ram-cgroup',action='store_true',
                        help='after the recorded AS-limit failure, enforce 32 GiB actual memory instead')
    args=parser.parse_args()
    work=args.work.resolve(); flow=args.orfs.resolve()/'flow'
    label=variant(args.seed,'pe'); output=work/label
    result=flow/'results/asap7/t10_reference_pe'/label
    with (work/f'eda_seed{args.seed}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        recovery_name='ram_cgroup_resume.inputs.json' if args.ram_cgroup else 'memory_resume.inputs.json'
        if (output/recovery_name).exists():
            raise RuntimeError('this infrastructure retry was already attempted; diagnose rather than restart')
        if args.ram_cgroup:
            previous=output/'memory_resume.inputs.json'
            if previous.is_file():
                if json.loads(previous.read_text())['original_inputs']['sha256']!=sha(output/'inputs.json'):
                    raise RuntimeError('previous AS-limit attempt has changed input provenance')
            elif json.loads((output/'runtime_resources.json').read_text())['max_address_space_bytes']!=int(31.75*1024**3):
                raise RuntimeError('missing provenance for the previous 31.75 GiB AS-limit attempt')
        if (output/'baseline.completed.json').exists() or (result/'5_2_route.odb').exists():
            raise RuntimeError('a completed route exists; do not overwrite it')
        old=output/'inputs.json'; inputs=json.loads(old.read_text())
        expected=dict(inputs)
        expected.update(seed=args.seed,block='pe',variant=label,threads=4,route_iterations=20,
                        rtl_sha256=sha(RTL),config_sha256=sha(HERE/BLOCKS['pe'][1]),
                        openroad=subprocess.check_output([shutil.which('openroad'),'-version'],text=True).strip(),
                        source_config_sha256={str(p.relative_to(HERE)):sha(p) for p in (HERE/'physical').rglob('*') if p.is_file()})
        if expected!=inputs or inputs['rtl_sha256']!=EXPECTED_RTL:
            raise RuntimeError('silicon inputs changed; cannot resume the same measured run')
        failure=output/'baseline.log'
        if 'Error: out of memory.' not in failure.read_text():
            raise RuntimeError('no terminal allocation failure; retry is not authorized by this helper')
        checkpoints={name:artifact(result/name) for name in ('5_1_grt.odb','5_1_grt.sdc','route.guide')}
        archive=output/('failed_as31p75gib' if args.ram_cgroup else 'failed_as30gib'); archive.mkdir(exist_ok=False)
        for path in (failure,flow/'logs/asap7/t10_reference_pe'/label/'5_2_route.log'):
            shutil.copyfile(path,archive/path.name)
        env=os.environ|dict(T10_V1_ROOT=str(HERE),T10_V1_RTL=str(RTL),T10_LAYOUT_SEED=str(args.seed),
                            PLATFORM_DIR=str(REPO/'vendor/asap7'),DETAILED_ROUTE_END_ITERATION='20',
                            T10_FP_DESIGN_NAME='t10_reference_pe',
                            T10_FP_CONSTRAINT=str(HERE/'physical/t10_frozen_fp_quad/constraint_classe.sdc'),
                            T10_FP_IO_CONSTRAINTS='',T10_FP_HOLD_SLACK_MARGIN='',
                            T10_MAX_AS_BYTES=str(int(31.75*1024**3)),MALLOC_ARENA_MAX='2')
        views={}
        for key,prefix in (('fp0','FP0'),('fp1','FP1'),('fp2','FP2'),('int','INT'),('cpa','CPA')):
            master=BLOCKS[key][0]; directory=flow/'results/asap7'/master/variant(args.seed,key)
            for suffix,filename in (('LEF',master+'_m7.lef'),('LIB',master+'_wc.lib')):
                path=directory/filename
                env[f'T10_{prefix}_{suffix}']=str(path)
                views[f'{prefix}_{suffix}']=artifact(path)
        scope=f't10-v1-seed{args.seed}-ram32'
        if args.ram_cgroup:
            env['T10_MAX_AS_BYTES']=str(-1)  # RLIM_INFINITY; cgroup controls actual usage.
        resources=dict(max_address_space_bytes=None if args.ram_cgroup else int(env['T10_MAX_AS_BYTES']),
                       malloc_arena_max='2',threads=4)
        if args.ram_cgroup:
            resources.update(memory_max_bytes=32*1024**3,memory_swap_max_bytes=0,cgroup_scope=scope+'.scope')
        record=dict(reason='terminal_allocator_failure_under_31p75GiB_RLIMIT_AS_use_actual_memory_limit' if args.ram_cgroup else 'terminal_allocator_failure_under_30GiB_RLIMIT_AS',
                    restarts_from='retained_global_route_not_iteration13',
                    original_inputs=artifact(old),checkpoints=checkpoints,macro_views=views,
                    failed_logs=[artifact(p) for p in archive.iterdir()],runtime_resources=resources)
        (output/recovery_name).write_text(json.dumps(record,indent=2)+'\n')
        command=['make',f'DESIGN_CONFIG={HERE/BLOCKS["pe"][1]}',f'FLOW_VARIANT={label}',
                 f'OPENROAD_EXE={shutil.which("openroad")}',f'YOSYS_EXE={shutil.which("yosys")}',
                 'NUM_CORES=4','route','do-finish']
        if args.ram_cgroup:
            command=['systemd-run','--user','--scope','--quiet','--unit='+scope,
                     '--property=MemoryMax=32G','--property=MemorySwapMax=0',*command]
        started=time.time()
        run(command,output/'baseline.log',env,flow)
        if any(sha(result/name)!=data['sha256'] for name,data in checkpoints.items()):
            raise RuntimeError('retained GRT inputs changed during retry')
        artifacts={name:dict(bytes=(result/name).stat().st_size,sha256=sha(result/name)) for name in baseline_files('pe','t10_reference_pe')}
        completed=dict(status='flow_completed_not_yet_qualified',result_dir=str(result),inputs_sha256=sha(old),
                       elapsed_seconds=time.time()-started,artifacts=artifacts,runtime_resources=resources,
                       memory_resume_inputs_sha256=sha(output/recovery_name))
        (output/'baseline.completed.json').write_text(json.dumps(completed,indent=2)+'\n')
        print('COMPLETE infrastructure retry; physical and power qualification still required',flush=True)


if __name__=='__main__':
    main()
