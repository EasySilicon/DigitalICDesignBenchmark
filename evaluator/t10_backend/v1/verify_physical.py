"""Qualify one completed reference seed; never qualify a partial three-seed set."""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess

from run_layout import BLOCKS, variant
from run_gate_activity import HISTORICAL
from measure_power import sha

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]


def artifact(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))


def limits():
    resource.setrlimit(resource.RLIMIT_AS,(30*1024**3,30*1024**3))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def run(command,log,env):
    print('RUN',log,flush=True)
    with log.open('w') as stream:
        subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,
                       env=env,check=True,preexec_fn=limits)


def number(path,pattern):
    match=re.search(pattern,path.read_text())
    if not match:
        raise ValueError(f'missing timing value: {path}')
    return float(match[1])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,choices=(11,29,47),required=True)
    parser.add_argument('--orfs',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--gc-plugin',type=Path,required=True)
    parser.add_argument('--seed11-repaired-final',type=Path)
    args=parser.parse_args()
    if args.seed==11 and args.seed11_repaired_final is None:
        parser.error('seed11 requires the repaired final directory')
    flow=args.orfs.resolve()/'flow'; work=args.work.resolve()
    base=work/f'seed{args.seed}_physical_verification'; base.mkdir(exist_ok=True)
    labels={key:HISTORICAL[key] if args.seed==11 else variant(args.seed,key) for key in BLOCKS}
    physical={key:flow/'results/asap7'/design/labels[key] for key,(design,_) in BLOCKS.items()}
    libs=sorted(p for p in (REPO/'vendor/asap7/lib/NLDM').glob('*RVT_SS_nldm_*') if 'FAKE' not in p.name)
    if len(libs)!=5:
        raise ValueError('expected five pinned WC libraries')
    blocks={}; failures={}
    for key,(design,_) in BLOCKS.items():
        out=base/key; out.mkdir(exist_ok=True)
        try:
            directory=physical[key]
            prefix='6_final'
            if key=='pe' and args.seed==11:
                directory=args.seed11_repaired_final.resolve(); prefix='v15_manual_final'
            inputs={kind:directory/f'{prefix}.{kind}' for kind in ('odb','sdc','spef')}
            inputs['netlist']=physical[key]/'6_final.v'
            inventory={kind:artifact(path) for kind,path in inputs.items()}
            used_libs=list(libs)
            if key=='pe':
                # The historical directory contains an older *_wc.lib too.
                # Its frozen 6_report.log used *.lib; bind to those exact
                # recorded hashes, never infer provenance from a suffix.
                suffix='.lib' if args.seed==11 else '_wc.lib'
                child_libs=[physical[child]/(BLOCKS[child][0]+suffix) for child in BLOCKS if child!='pe']
                if args.seed==11:
                    expected=json.loads((REPO/'evaluator/t10_pe_reference_probe.json').read_text())['inputs']['macro_lib_sha256']
                    if [sha(p) for p in child_libs]!=expected:
                        raise ValueError('historical seed11 macro timing library hashes drifted')
                used_libs+=child_libs
            env=os.environ|{'T10_LIBRARY_LIST':' '.join('{'+str(p)+'}' for p in used_libs),
                            'T10_VERIFY_OUTPUT':str(out)}
            env.update({'T10_INPUT_'+kind.upper():str(path) for kind,path in inputs.items() if kind!='netlist'})
            run(['openroad','-exit','-no_init','-no_splash',str(HERE/'verify_extracted.tcl')],out/'sta.log',env)
            values={name:number(out/(name+'.rpt'),r'worst slack (?:max|min)\s+([-+\d.eE]+)') for name in ('setup','hold')}
            values.update({name:number(out/(name+'.rpt'),r'tns (?:max|min)\s+([-+\d.eE]+)') for name in ('setup_tns','hold_tns')})
            for kind in ('internal_setup','internal_hold'):
                values[kind]=number(out/(kind+'.rpt'),r'([-+\d.eE]+)\s+slack \((?:MET|VIOLATED)\)')
                if values[kind]<0:
                    raise ValueError(f'{key} {kind} fails: {values[kind]} ps')
            if (out/'constraint_coverage.rpt').read_text().strip() or (out/'antenna.rpt').read_text().strip():
                raise ValueError('constraint coverage or antenna report is nonempty')
            if key=='pe' and (min(values['setup'],values['hold'])<0 or values['setup_tns']!=0 or values['hold_tns']!=0):
                raise ValueError(f'PE extracted timing fails: {values}')
            connection=out/'geometric_connectivity.json'
            run(['openroad','-exit','-no_init','-python',str(HERE/'check_connectivity.py'),str(inputs['odb']),str(connection)],out/'connectivity.log',os.environ)
            connectivity=json.loads(connection.read_text())
            if connectivity['status']!='passed' or connectivity['odb']['sha256']!=inventory['odb']['sha256']:
                raise ValueError('connectivity input or result mismatch')
            route_log=flow/'logs/asap7'/design/labels[key]/'5_2_route.log'
            if '[INFO DRT-0198] Complete detail routing.' not in route_log.read_text() or '[ERROR ' in route_log.read_text():
                raise ValueError('original detailed routing did not complete cleanly')
            drc=flow/'reports/asap7'/design/labels[key]/'5_route_drc.rpt'
            if key=='pe':
                drc=out/'final_drc.rpt'
                env=os.environ|{'T10_INPUT_ODB':str(inputs['odb']),'T10_DRC_REPORT':str(drc),'T10_PATCH_SO':str(args.gc_plugin.resolve())}
                run(['openroad','-exit','-no_init','-no_splash',str(HERE.parent/'physical/t10_manual_v15_gc_full.tcl')],out/'drc.log',env)
                if not re.search(r'T10_FULL_CHECK workers=\d+ raw_unique=\d+ checked_scope=0 context_only=\d+ DRCSAFEDIST=500 MTSAFEDIST=4000', (out/'drc.log').read_text()):
                    raise ValueError('whole-PE native DRC did not pass')
            if drc.stat().st_size:
                raise ValueError(f'nonzero DRC: {drc}')
            metric=flow/'logs/asap7'/design/labels[key]/'6_report.json'
            area=json.loads(metric.read_text())['finish__design__instance__area']
            if not area>0:
                raise ValueError('nonpositive physical area')
            reports={name:artifact(out/(name+'.rpt')) for name in ('setup','hold','setup_tns','hold_tns','internal_setup','internal_hold','constraint_coverage','antenna','electrical')}
            reports.update(connectivity=artifact(connection),drc=artifact(drc),original_route_log=artifact(route_log),original_finish_metrics=artifact(metric))
            block=dict(status='qualified',design=design,area_um2=area,timing_ps=values,inputs=inventory,reports=reports,
                       wc_libraries=[artifact(p) for p in used_libs])
            (out/'block.json').write_text(json.dumps(block,indent=2)+'\n')
            blocks[key]=block
            print('PHYSICAL BLOCK PASSED',args.seed,key,flush=True)
        except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
            failures[key]=str(error)
            print('PHYSICAL BLOCK FAILED',args.seed,key,str(error),flush=True)
    result=dict(task_id='T10',measurement_scope='single_pe',layout_seed=args.seed,
                status='single_seed_physical_qualified' if len(blocks)==6 and not failures else 'physical_qualification_failed',
                blocks=blocks,failures=failures,checker_sha256=sha(Path(__file__)),
                gc_plugin=artifact(args.gc_plugin.resolve()))
    (base/'physical.json').write_text(json.dumps(result,indent=2)+'\n')
    if failures or len(blocks)!=6:
        raise SystemExit(1)


if __name__=='__main__':
    main()
