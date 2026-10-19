"""Re-extract an audited local repair, preserve originals, then install it.

Does not claim physical qualification or edit the historical completion marker.
The unchanged physical/activity/power pipeline must subsequently pass in full.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil

from resume_after_oom import artifact
from run_layout import BLOCKS, HERE, REPO, run, sha, variant


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,choices=(29,47),required=True)
    parser.add_argument('--orfs',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--repair',type=Path,required=True)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--audit',type=Path)
    parser.add_argument('--original',type=Path)
    parser.add_argument('--control',type=Path)
    parser.add_argument('--previous-repair',type=Path)
    args=parser.parse_args()
    seed=args.seed; work=args.work.resolve(); repair=args.repair.resolve()
    repair.mkdir(parents=True,exist_ok=True)
    flow=args.orfs.resolve()/'flow'; label=variant(seed,'pe')
    original=flow/'results/asap7/t10_reference_pe'/label
    source=args.original.resolve() if args.original else original
    marker=work/label/'baseline.completed.json'
    record=json.loads(marker.read_text())
    if record['status']!='flow_completed_not_yet_qualified':
        raise ValueError('original physical flow has not completed')
    for name,saved in record['artifacts'].items():
        path=source/name
        if path.stat().st_size!=saved['bytes'] or sha(path)!=saved['sha256']:
            raise ValueError('original completed output changed: '+name)
    audit_path=args.audit.resolve() if args.audit else repair/'invariants.json'
    audit=json.loads(audit_path.read_text())
    candidate=args.candidate.resolve() if args.candidate else repair/'repaired.odb'
    if audit.get('wire_iterator_policy')!='OpenDB_paths_plus_explicit_RECT_decoder' or \
            audit['status']!='passed' or audit['before']['sha256']!=sha(source/'6_final.odb') or \
            audit['after']['sha256']!=sha(candidate):
        raise ValueError('repair invariant audit does not bind the actual checkpoints')
    canonical_physical=work/f'seed{seed}_physical_verification'
    physical=args.control.resolve() if args.control else canonical_physical
    if source!=original:
        if not args.previous_repair:
            raise ValueError('replacing a previous prototype requires its exact record')
        previous=json.loads(args.previous_repair.read_text())
        if sha(original/'6_final.odb')!=previous['candidate_odb']['sha256'] or \
                sha(original/'6_final.spef')!=previous['candidate_spef']['sha256'] or \
                sha(original/'6_final.v')!=record['artifacts']['6_final.v']['sha256'] or \
                sha(original/'6_final.sdc')!=record['artifacts']['6_final.sdc']['sha256']:
            raise ValueError('current prototype changed; cannot replace it')
    control=json.loads((physical/'physical.json').read_text())
    if control['status']!='physical_qualification_failed' or set(control['failures'])!={'pe'} or \
            set(control['blocks'])!={'fp0','fp1','fp2','int','cpa'}:
        raise ValueError('expected original PE-only failure and qualified internal macros')
    drc=re.search(r'T10_FULL_CHECK workers=\d+ raw_unique=\d+ checked_scope=(\d+) context_only=\d+',
                  (physical/'pe/drc.log').read_text())
    if not drc or int(drc[1])<=0:
        raise ValueError('missing native whole-PE negative control')
    if json.loads((physical/'pe/geometric_connectivity.json').read_text())['odb']['sha256']!=sha(source/'6_final.odb'):
        raise ValueError('negative control does not match original geometry')
    if (repair/'extraction.inputs.json').exists() or (repair/'original').exists() or (repair/'physical_before').exists():
        raise ValueError('manual installation already attempted; preserve and inspect, do not repeat')
    libraries=sorted(p for p in (REPO/'vendor/asap7/lib/NLDM').glob('*RVT_SS_nldm_*') if 'FAKE' not in p.name)
    if len(libraries)!=5:
        raise ValueError('expected five fixed WC cell libraries')
    libraries += [flow/'results/asap7'/BLOCKS[key][0]/variant(seed,key)/(BLOCKS[key][0]+'_wc.lib')
                  for key in BLOCKS if key!='pe']
    inputs=dict(layout_seed=seed,patched_odb=artifact(candidate),sdc=artifact(source/'6_final.sdc'),
                libraries=[artifact(p) for p in libraries],rc_rules=artifact(REPO/'vendor/asap7/rcx_patterns.rules'),
                set_rc=artifact(REPO/'vendor/asap7/setRC.tcl'),script=artifact(HERE/'extract_manual.tcl'))
    (repair/'extraction.inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    env=os.environ|dict(T10_LIBRARY_LIST=' '.join('{'+str(p)+'}' for p in libraries),
                        T10_INPUT_ODB=str(candidate),T10_INPUT_SDC=str(source/'6_final.sdc'),
                        T10_OUTPUT_SPEF=str(repair/'repaired.spef'),T10_PLATFORM=str(REPO/'vendor/asap7'),
                        T10_ORFS_FLOW=str(flow),T10_MANUAL_DIR=str(repair),T10_MAX_AS_BYTES='-1',MALLOC_ARENA_MAX='2')
    run(['systemd-run','--user','--scope','--quiet',f'--unit=t10-manual-seed{seed}-{repair.name}-rcx',
         '--property=MemoryMax=32G','--property=MemorySwapMax=0','openroad','-exit','-no_init',
         str(HERE/'extract_manual.tcl')],repair/'extract.log',env,REPO)
    for name in ('setup','hold','setup_tns','hold_tns'):
        text=(repair/(name+'.rpt')).read_text()
        match=re.search(r'(?:worst slack (?:max|min)|tns (?:max|min))\s+([-+\d.eE]+)',text)
        if not match or (float(match[1])<0 if not name.endswith('tns') else float(match[1])!=0):
            raise ValueError('repaired extracted timing fails: '+name)
    archive=repair/'original'; archive.mkdir()
    originals={}
    for name in record['artifacts']:
        shutil.copyfile(source/name,archive/name)
        originals[name]=artifact(archive/name)
    shutil.copyfile(marker,archive/'baseline.completed.json')
    # Keep original report paths/contents as history, with fresh explicit
    # locations for the negative-control files in the installation record.
    if physical==canonical_physical:
        physical.rename(repair/'physical_before')
    else:
        shutil.copytree(physical,repair/'physical_before')
        if canonical_physical.exists():
            canonical_physical.rename(repair/'physical_previous_attempt')
    shutil.copyfile(candidate,original/'6_final.odb')
    shutil.copyfile(repair/'repaired.spef',original/'6_final.spef')
    installed=dict(status='manual_repair_installed_not_yet_qualified',layout_seed=seed,
                   original_artifacts=originals,invariants=artifact(audit_path),
                   extraction_inputs=artifact(repair/'extraction.inputs.json'),extraction_log=artifact(repair/'extract.log'),
                   candidate_odb=artifact(candidate),candidate_spef=artifact(repair/'repaired.spef'),
                   original_native_drc_count=int(drc[1]),
                   negative_control={name:artifact(repair/'physical_before/pe'/name)
                                     for name in ('drc.log','final_drc.rpt','final_drc.rpt.raw')},
                   original_completion_marker=artifact(archive/'baseline.completed.json'))
    if args.previous_repair:
        installed['previous_repair']=artifact(args.previous_repair)
        installed['previous_native_drc']=artifact(repair/'physical_previous_attempt/pe/final_drc.rpt')
    (repair/'manual_repair.json').write_text(json.dumps(installed,indent=2)+'\n')
    active=work/f'seed{seed}_manual_repair'
    if repair!=active:
        pointer=active/'active_repair.json'
        if pointer.exists():
            shutil.copyfile(pointer,repair/'previous_active_repair.json')
        pointer.write_text(json.dumps(artifact(repair/'manual_repair.json'),indent=2)+'\n')
    print('INSTALLED audited repair; original outputs preserved; full physical and power checks required',flush=True)


if __name__=='__main__':
    main()
