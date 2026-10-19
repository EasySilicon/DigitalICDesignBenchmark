"""Finish physical/activity/power checks after one identified layout job.

Each seed tracks its own producer, so another seed's terminal failure cannot
silently strand it. No automatic physical retries and no three-seed claim.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from run_layout import HERE, REPO, EXPECTED_RTL, variant
from measure_power import sha


def check_activity(activity,physical,shell_sha):
    if activity.get('numerical_oracle_passed') is not True or activity.get('protocol_and_latency_passed') is not True or \
            activity.get('completed_matrix_blocks')!=200 or activity.get('output_points_checked')!=51200 or \
            activity.get('reference_rtl_sha256')!=EXPECTED_RTL or activity.get('layout_seed')!=physical['layout_seed']:
        raise ValueError('activity is not the checked full frozen gate workload')
    netlists={row['block']:row for row in activity['netlists']}
    if len(netlists)!=7 or len(activity['netlists'])!=7 or set(netlists)!={'shell',*physical['blocks']}:
        raise ValueError('incomplete gate-model source inventory')
    if netlists['shell']['sha256']!=shell_sha:
        raise ValueError('mapped full-DUT shell changed')
    for key,block in physical['blocks'].items():
        if netlists[key]['sha256']!=block['inputs']['netlist']['sha256']:
            raise ValueError(f'activity does not match physical {key} gate netlist')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,choices=(29,47),required=True)
    parser.add_argument('--producer-pid',type=int,required=True)
    parser.add_argument('--orfs',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--gate-shell',type=Path,required=True)
    parser.add_argument('--gc-plugin',type=Path,required=True)
    args=parser.parse_args()
    work=args.work.resolve(); seed=args.seed
    done=work/variant(seed,'pe')/'baseline.completed.json'
    proc=Path(f'/proc/{args.producer_pid}/stat')
    identity=proc.read_text().split()[21] if proc.exists() else None
    def live():
        try:
            return identity is not None and proc.read_text().split()[21]==identity
        except FileNotFoundError:
            return False
    print('WAIT completed layout seed',seed,'producer',args.producer_pid,flush=True)
    while not done.exists():
        if not live():
            raise RuntimeError('identified layout producer stopped before completion')
        time.sleep(15)
    marker=json.loads(done.read_text())
    if marker['status']!='flow_completed_not_yet_qualified' or marker['inputs_sha256']!=sha(done.parent/'inputs.json'):
        raise ValueError('layout completion provenance mismatch')
    def run(script,*options):
        subprocess.run(['python3',str(HERE/script),*map(str,options)],check=True,cwd=REPO)
    run('verify_physical.py','--seed',seed,'--orfs',args.orfs,'--work',work,'--gc-plugin',args.gc_plugin)
    physical_path=work/f'seed{seed}_physical_verification/physical.json'
    physical=json.loads(physical_path.read_text())
    if physical['status']!='single_seed_physical_qualified':
        raise ValueError('physical reference gates are not qualified')
    run('verify_full_geometry.py','--physical',physical_path,'--output',work/f'seed{seed}_full_geometry')
    out=work/f'seed{seed}_activity_directnets'
    manifest=out/'activity_manifest.json'
    if not manifest.exists():
        options=['--seed',seed,'--label','activity_directnets','--staged','--pe-only-trace','--windowed-saif',
                 '--orfs',args.orfs,'--work',work,'--gate-shell',args.gate_shell]
        if (out/'staged_build_manifest.json').exists():
            options.append('--reuse-build')
        run('run_gate_activity.py',*options)
    activity=json.loads(manifest.read_text())
    check_activity(activity,physical,sha(args.gate_shell))
    if sha(out/'activity.saif')!=activity['activity_sha256']:
        raise ValueError('raw activity changed')
    audit=out/'merge_audit.json'
    if not audit.exists():
        run('merge_pe_saif.py','--input',out/'activity.saif','--shell',out/'shell.v','--pe',out/'pe.v',
            '--output',out/'average.saif','--audit',audit)
    run('measure_power.py','--seed',seed,'--orfs',args.orfs,'--activity-manifest',manifest,
        '--merge-audit',audit,'--saif',out/'average.saif','--output',work/f'seed{seed}_power')
    power=work/f'seed{seed}_power/power.json'
    record=dict(status='single_seed_complete_not_three_seed_baseline',layout_seed=seed,
                physical_sha256=sha(physical_path),power_sha256=sha(power),activity_manifest_sha256=sha(manifest))
    (work/f'seed{seed}_complete.json').write_text(json.dumps(record,indent=2)+'\n')
    print('COMPLETE CHECKED SEED',seed,'; three-seed baseline still requires final audit',flush=True)


if __name__=='__main__':
    main()
