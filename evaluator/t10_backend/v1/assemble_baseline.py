"""Audit all three real seeds before writing a reference or scoring record.

Does not edit the authoritative baselines. Missing/failed seeds, changed
artifacts, incomplete activity, or scope mismatches produce no output files.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
import yaml

from jsonschema import Draft202012Validator
from run_layout import HERE, REPO, RTL, EXPECTED_RTL
from measure_power import sha
from complete_seed import check_activity
from saif_window import POLICY as WINDOW_POLICY

sys.path.insert(0,str(REPO/'evaluator'))
from score_run import expected_ppa_parameters, ppa_provenance_valid
from ppa_aggregate import source_hash

SEEDS=(11,29,47)


def read(path):
    return json.loads(path.read_text())


def artifact(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))


def check_artifacts(value):
    if isinstance(value,dict):
        if {'path','bytes','sha256'}<=value.keys():
            path=Path(value['path'])
            if not path.is_absolute():
                path=REPO/path
            if path.stat().st_size!=value['bytes'] or sha(path)!=value['sha256']:
                raise ValueError(f'changed artifact: {path}')
        for child in value.values():
            check_artifacts(child)
    elif isinstance(value,list):
        for child in value:
            check_artifacts(child)


def positive(value):
    return type(value) in (int,float) and math.isfinite(value) and value>0


def check_archived_invariant(invariant,manual):
    # Installation replaces the canonical checkpoint, not the historical
    # audit. Resolve its before-image only to the hash-bound archived original.
    archived=manual['original_artifacts']['6_final.odb']
    before=invariant['before']
    if any(before[key]!=archived[key] for key in ('bytes','sha256')):
        raise ValueError('invariant before-image differs from archived original')
    check_artifacts(dict(invariant,before=archived))


def qualify_seed(work,seed):
    directory=work/f'seed{seed}_physical_verification'
    phy_path=directory/'physical.json'; power_path=work/f'seed{seed}_power/power.json'
    activity_dir=work/f'seed{seed}_activity_directnets'
    manifest_path=activity_dir/'activity_manifest.json'; audit_path=activity_dir/'merge_audit.json'
    physical,power,activity,audit=map(read,(phy_path,power_path,manifest_path,audit_path))
    full_path=work/f'seed{seed}_full_geometry/full_geometry.json'
    full=read(full_path)
    if full['status']!='single_seed_all_geometry_passed' or full['layout_seed']!=seed or \
            full['physical_sha256']!=sha(phy_path) or full['checker_sha256']!=sha(HERE/'verify_full_geometry.py') or \
            set(full['blocks'])!={'fp0','fp1','fp2','int','cpa','pe'}:
        raise ValueError('missing complete RECT-aware six-block geometry proof')
    check_artifacts(full)
    for key,record in full['blocks'].items():
        data=read(Path(record['path']))
        if data['status']!='passed' or data['wire_iterator_policy']!='OpenDB_paths_plus_explicit_RECT_decoder' or \
                data['checker_sha256']!=sha(HERE/'check_connectivity_full.py') or data['iterator_sha256']!=sha(HERE/'full_geometry.py') or \
                data['union_algorithm_sha256']!=sha(HERE/'check_connectivity.py') or \
                data['odb']['sha256']!=physical['blocks'][key]['inputs']['odb']['sha256']:
            raise ValueError('full-geometry checker/input provenance mismatch')
    if physical.get('status')!='single_seed_physical_qualified' or physical.get('layout_seed')!=seed or physical.get('failures') or \
            set(physical['blocks'])!={'pe','fp0','fp1','fp2','int','cpa'}:
        raise ValueError(f'seed {seed} physical qualification incomplete')
    if physical['checker_sha256']!=sha(HERE/'verify_physical.py'):
        raise ValueError('physical checker version changed')
    check_artifacts(physical)
    for key,block in physical['blocks'].items():
        t=block['timing_ps']; reports=block['reports']
        if block['status']!='qualified' or reports['drc']['bytes'] or reports['constraint_coverage']['bytes'] or \
                min(t['internal_setup'],t['internal_hold'])<0 or not positive(block['area_um2']):
            raise ValueError(f'seed {seed} {key} physical gates fail')
        connection=read(Path(reports['connectivity']['path']))
        if connection['status']!='passed' or connection['failures'] or connection['signal_nets_checked']<=0 or \
                connection['odb']['sha256']!=block['inputs']['odb']['sha256'] or \
                connection['checker_sha256']!=sha(HERE/'check_connectivity.py'):
            raise ValueError('physical connectivity provenance mismatch')
    pe=physical['blocks']['pe']; timing=pe['timing_ps']
    if min(timing['setup'],timing['hold'])<0 or timing['setup_tns'] or timing['hold_tns']:
        raise ValueError('PE extracted timing fails')
    drc_log=directory/'pe/drc.log'; drc_raw=directory/'pe/final_drc.rpt.raw'
    if not re.search(r'T10_FULL_CHECK workers=\d+ raw_unique=\d+ checked_scope=0 context_only=\d+ DRCSAFEDIST=500 MTSAFEDIST=4000',drc_log.read_text()):
        raise ValueError('whole-PE native DRC coverage is not proven')
    shell=next(row for row in activity['netlists'] if row['block']=='shell')
    check_activity(activity,physical,sha(Path(shell['path'])))
    for model in activity['simulation_cell_models']:
        if sha(Path(model['original']))!=model['sha256']:
            raise ValueError('simulation standard-cell model changed')
    staged_path=activity_dir/'staged_build_manifest.json'
    staged=read(staged_path)
    if sha(staged_path)!=activity['staged_build_manifest_sha256'] or staged['planning_sources_used_for_simulation'] is not False:
        raise ValueError('gate compilation provenance changed or planning stubs were used')
    for module in staged['modules']:
        if sha(Path(module['source']))!=module['source_sha256'] or sha(Path(module['args_file']))!=module['args_sha256']:
            raise ValueError('compiled gate module source/arguments changed')
    writer=activity['saif_writer']
    if sha(Path(writer['native_source']))!=writer['native_sha256'] or sha(HERE/'saif_window.py')!=writer['adapter_sha256'] or \
            sha(activity_dir/'saif_window/t10_saif_window.cpp')!=writer['corrected_sha256'] or \
            sha(activity_dir/'build/Vtb_hidden_T10_stream_windowed')!=writer['executable_sha256']:
        raise ValueError('actual SAIF runtime or gate executable changed')
    if activity['workload_manifest_sha256']!=sha(work/'workload/manifest.json') or \
            activity.get('saif_writer',{}).get('policy')!=WINDOW_POLICY or \
            sha(activity_dir/'activity.saif')!=activity['activity_sha256'] or \
            audit['source_sha256']!=activity['activity_sha256'] or audit['pe_instances']!=256 or \
            len(set(audit['pe_paths']))!=256 or audit['per_instance_weight']!=1/256 or \
            audit['output_sha256']!=sha(activity_dir/'average.saif') or \
            audit['duration_merged_ticks']!=audit['duration_per_instance_ticks']*256:
        raise ValueError('incomplete or changed 256-PE activity')
    if power.get('status')!='single_seed_activity_power_qualified_not_three_seed_baseline' or \
            power.get('measurement_scope')!='single_pe' or power.get('layout_seed')!=seed or power.get('power_corner')!='TT' or \
            power['workload_id']!='T10-power-v1' or power['matrix_blocks']!=200 or power['instance_weights']!={'pe':1} or power['activity_manifest_sha256']!=sha(manifest_path) or \
            power['merge_audit_sha256']!=sha(audit_path) or power['merged_saif_sha256']!=audit['output_sha256']:
        raise ValueError('power/source/scope mismatch')
    check_artifacts(power)
    for path,digest in power['tt_standard_libraries'].items():
        if sha(Path(path))!=digest or '_RVT_TT_' not in path or 'FAKE' in path:
            raise ValueError('incorrect TT standard-cell library')
    if len(power['tt_standard_libraries'])!=5 or len(power['tt_macro_abstracts'])!=5:
        raise ValueError('incomplete TT models')
    pieces=power['components']
    if len(pieces)!=10 or len({row['instance'] for row in pieces})!=10 or \
            {row['instance'] for row in pieces}!={'pe_shell',*audit['physical_child_masters']}:
        raise ValueError('power does not cover shell and nine internal macros')
    by_master={block['design']:block for block in physical['blocks'].values()}
    for piece in pieces:
        block=by_master[piece['master']]
        if not positive(piece['power_w']) or not .95<=piece['activity_annotation_fraction']<=1 or \
                not .95<=piece['sequential_activity_annotation_fraction']<=1:
            raise ValueError('power annotation or component value fails')
        if sha(Path(piece['report_path']))!=piece['report_sha256']:
            raise ValueError('power report changed')
        report=Path(piece['report_path']).read_text()
        def reported(label):
            match=re.search(r'^'+label+r'\s+\S+\s+\S+\s+\S+\s+(\S+)',report,re.M)
            if not match:
                raise ValueError('power report missing '+label)
            return float(match[1])
        measured=reported('Total')-(reported('Macro') if piece['instance']=='pe_shell' else 0)
        if not math.isclose(measured,piece['power_w'],rel_tol=1e-9):
            raise ValueError('component power differs from native report')
        expected_scope='pe' if piece['instance']=='pe_shell' else 'pe/'+piece['instance']
        if piece['scope']!=expected_scope or (piece['instance']!='pe_shell' and piece['master']!=audit['physical_child_masters'][piece['instance']]):
            raise ValueError('component activity scope/master mismatch')
        if sha(Path(piece['report_path']).parent/'activity_nets.tsv')!=piece['activity_net_data_sha256']:
            raise ValueError('physical-net activity data changed')
        if any(piece['artifacts'][kind]['sha256']!=block['inputs'][kind]['sha256'] for kind in ('odb','sdc','spef')):
            raise ValueError('power measured different physical checkpoint')
    duration=power['vcd_window_seconds']; watts=power['total_power_w']; energy=power['energy_j_per_block']
    if not all(positive(v) for v in (duration,watts,energy)) or \
            not math.isclose(sum(p['power_w'] for p in pieces),watts,rel_tol=1e-9) or \
            not math.isclose(sum(power['components_w'].values()),watts,rel_tol=1e-9) or \
            not math.isclose(watts*duration/200,energy,rel_tol=1e-12):
        raise ValueError('incorrect complete-PE power/energy accounting')
    if audit['timescale']!='1ps' or not math.isclose(duration,audit['duration_per_instance_ticks']*1e-12,rel_tol=1e-12) or \
            abs(audit['clock_activity'][2]/(duration*256)-2e9)>2/duration:
        raise ValueError('activity clock/window is not 1 GHz')
    artifacts={kind:pe['inputs'][kind] for kind in ('odb','sdc','spef','netlist')}
    artifacts.update(timing_report=artifact(directory/'pe/block.json'),drc_report=pe['reports']['drc'],
                     constraint_report=pe['reports']['constraint_coverage'],connectivity_report=pe['reports']['connectivity'],
                     electrical_report=pe['reports']['electrical'],drc_raw_report=artifact(drc_raw),drc_log=artifact(drc_log),
                     full_geometry=artifact(full_path),full_connectivity=full['blocks']['pe'])
    if seed in (29,47):
        layout=work/f'ic_t10_v1_v15_seed{seed}_pe'
        for name in ('inputs.json','baseline.completed.json'):
            artifacts['layout_'+name.removesuffix('.json')]=artifact(layout/name)
        recovery=layout/('memory_resume.inputs.json' if seed==29 else 'placement_resume.inputs.json')
        check_artifacts(read(recovery))
        artifacts['layout_recovery']=artifact(recovery)
        ram_recovery=layout/'ram_cgroup_resume.inputs.json'
        if ram_recovery.exists():
            check_artifacts(read(ram_recovery))
            artifacts['ram_limit_recovery']=artifact(ram_recovery)
            confirmed=layout/'ram_cgroup_confirmed.json'
            limits=read(confirmed)
            if limits['memory_max_bytes']!=32*1024**3 or limits['memory_swap_max_bytes']!=0 or \
                    limits['max_address_space']!='unlimited':
                raise ValueError('actual RAM-limit enforcement not confirmed')
            artifacts['ram_limit_confirmation']=artifact(confirmed)
        if seed==47:
            log=layout/'manual_placement.log'
            if 'T10_MANUAL_PLACEMENT_PASS one_cell_only all_instances_and_connections_checked=68837' not in log.read_text():
                raise ValueError('missing measured seed47 exact-change and native placement checks')
            artifacts['placement_repair_log']=artifact(log)
        manual_path=work/f'seed{seed}_manual_repair/manual_repair.json'
        pointer=manual_path.with_name('active_repair.json')
        if pointer.exists():
            selected=read(pointer); check_artifacts(selected)
            manual_path=Path(selected['path'])
            artifacts['manual_repair_selection']=artifact(pointer)
        if manual_path.exists():
            manual=read(manual_path)
            check_artifacts(manual)
            invariant=read(Path(manual['invariants']['path']))
            check_archived_invariant(invariant,manual)
            if invariant.get('wire_iterator_policy')!='OpenDB_paths_plus_explicit_RECT_decoder' or invariant['status']!='passed' or \
                    invariant['before']['sha256']!=manual['original_artifacts']['6_final.odb']['sha256'] or \
                    invariant['after']['sha256']!=manual['candidate_odb']['sha256'] or \
                    manual['candidate_odb']['sha256']!=pe['inputs']['odb']['sha256'] or \
                    manual['candidate_spef']['sha256']!=pe['inputs']['spef']['sha256'] or \
                    manual['original_native_drc_count']<=0:
                raise ValueError('manual repair does not bind original, exact-change audit and qualified checkpoint')
            artifacts['manual_repair']=artifact(manual_path)
    level=dict(area_um2=pe['area_um2'],setup_worst_slack_ps=timing['setup'],hold_worst_slack_ps=timing['hold'],drc_violations=0,artifacts=artifacts)
    workload=work/'workload/manifest.json'
    power=dict(power,workload_sha256=sha(workload),artifacts=dict(workload_manifest=artifact(workload),activity_audit=artifact(audit_path),power_report=artifact(power_path)))
    row=dict(layout_seed=seed,levels={'pe':level},area_um2=pe['area_um2'],delay_ps=1000-timing['setup'],power=power,
             physical_record=artifact(phy_path),activity_manifest=artifact(manifest_path))
    normal=dict(layout_seed=seed,measurement_scope='single_pe',area_um2=pe['area_um2'],delay_ns=row['delay_ps']/1000,
                setup_worst_slack_ns=timing['setup']/1000,hold_worst_slack_ns=timing['hold']/1000,drc_violations=0,
                energy_per_op_pj=energy*1e12,power_w=watts,average_power_mw=watts*1000,ops=200,
                annotation_fraction=power['activity_annotation_fraction'],physical_record_sha256=sha(phy_path),power_record_sha256=sha(power_path))
    return row,normal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--orfs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); work=args.work.resolve(); output=args.output.resolve()
    required=[work/f'seed{s}_{suffix}' for s in SEEDS for suffix in ('physical_verification/physical.json','power/power.json','activity_directnets/activity_manifest.json','activity_directnets/merge_audit.json','full_geometry/full_geometry.json')]
    missing=[str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError('three-seed evidence incomplete: '+', '.join(missing))
    if sha(RTL)!=EXPECTED_RTL:
        raise ValueError('frozen v15 RTL changed')
    rows,normalized=zip(*(qualify_seed(work,seed) for seed in SEEDS))
    fixture=REPO/'evaluator/fixtures/t10_v1_three_seed'
    structure=read(fixture/'v15_structure.json'); component=read(fixture/'component_source_audit.json')
    if not structure['passed'] or structure['pe_instances']!=256 or structure['mesh_paths']!=[16,16] or \
            structure['rtl_sha256']!=EXPECTED_RTL or structure['checker_sha256']!=sha(REPO/'evaluator/t10_structure_check.py') or \
            structure['filelist_sha256']!=sha(RTL.parent/'files.f'):
        raise ValueError('frozen structure is not qualified')
    inventory={str(p.relative_to(REPO)):sha(p) for p in sorted(HERE.parent.rglob('*')) if p.suffix in ('.py','.tcl','.cc','.mk')}
    for name in ('evaluator/score_run.py','evaluator/ppa_power_probe.py','evaluator/make_t10_power_vectors.py','evaluator/t10_structure_check.py','benchmark/tasks/T10/ppa.md','benchmark/tasks/T10/ppa-evidence.schema.json','env/orfs-26q2-compat.patch'):
        inventory[name]=sha(REPO/name)
    inventory_text=json.dumps(inventory,sort_keys=True,indent=2)+'\n'
    evaluator_sha=hashlib.sha256(inventory_text.encode()).hexdigest()
    workload=read(work/'workload/manifest.json')
    if workload['task_id']!='T10' or workload['seed']!=20260925 or workload['case_count']!=200 or \
            workload['oracle_check']['status']!='pass' or \
            workload['oracle_check']['oracle_sha256']!=sha(REPO/workload['oracle_check']['oracle_path']):
        raise ValueError('fixed workload/oracle contract changed')
    for name,record in workload['files'].items():
        path=work/'workload'/name
        if path.stat().st_size!=record['bytes'] or sha(path)!=record['sha256']:
            raise ValueError('workload vector changed: '+name)
    vector_digest=hashlib.sha256()
    for name in ('a','b','as','bs','mode','phase'):
        payload=(work/'workload'/f'{name}.mem').read_bytes()
        vector_digest.update(name.encode()); vector_digest.update(len(payload).to_bytes(8,'big')); vector_digest.update(payload)
    aggregate={key:statistics.median(row[key] for row in normalized) for key in ('area_um2','delay_ns','energy_per_op_pj','average_power_mw')}
    aggregate['annotation_fraction']=min(row['annotation_fraction'] for row in normalized)
    params=expected_ppa_parameters('T10')
    toolchain=dict(yosys=subprocess.check_output(['yosys','-V'],text=True).strip(),openroad=subprocess.check_output(['openroad','-version'],text=True).strip(),
                   orfs_revision=subprocess.check_output(['git','-C',str(args.orfs),'rev-parse','HEAD'],text=True).strip(),
                   asap7_manifest_sha256=sha(REPO/'vendor/asap7/SHA256SUMS'),evaluator_sha256=evaluator_sha)
    lock=yaml.safe_load((REPO/'benchmark/sources.lock.yaml').read_text())
    actual_diff=subprocess.check_output(['git','-C',str(args.orfs),'diff','--','flow/scripts/final_outputs.tcl'])
    dirty=subprocess.check_output(['git','-C',str(args.orfs),'diff','--name-only','HEAD'],text=True).splitlines()
    if toolchain['orfs_revision']!=lock['ppa']['flow_revision'] or dirty!=['flow/scripts/final_outputs.tcl'] or \
            actual_diff!=(REPO/'env/orfs-26q2-compat.patch').read_bytes():
        raise ValueError('ORFS source differs from locked revision and reviewed compatibility patch')
    toolchain['orfs_compat_patch_sha256']=sha(REPO/'env/orfs-26q2-compat.patch')
    pe_hash=next(row['v15_sha256'] for row in component['components'] if row['module']==structure['pe_module'])
    evidence=dict(schema_version=2,task_id='T10',measurement_scope='single_pe',measurement_status='three_seed_single_pe',
                  toolchain=toolchain,parameter_set=params,
                  workload=dict(id='T10-power-v1',matrix_blocks=200,sha256=sha(work/'workload/manifest.json'),oracle_sha256=workload['oracle_check']['oracle_sha256']),
                  source=dict(rtl_sha256=EXPECTED_RTL,filelist_sha256=sha(RTL.parent/'files.f'),structure_report_sha256=sha(fixture/'v15_structure.json'),
                              pe_rtl_sha256=pe_hash,pe_module=structure['pe_module'],hierarchy=dict(tile_instances=16,pe_instances_per_tile=16,pe_instances_total=256),
                              legacy_component_audit_sha256=sha(fixture/'component_source_audit.json')),
                  per_seed=list(rows),aggregate=aggregate)
    schema=read(REPO/'benchmark/tasks/T10/ppa-evidence.schema.json'); Draft202012Validator(schema).validate(evidence)
    reference=dict(task_id='T10',qualification_status='qualified_1ghz',measurement_status='three_seed_single_pe',measurement_scope='single_pe',
                   source_sha256=source_hash(RTL.parent.parent),frozen_reference_path='evaluator/reference/T10_v15',
                   workload_id='T10-power-v1',workload_sha256=evidence['workload']['sha256'],
                   workload_parameters=dict(seed=workload['seed'],case_count=200,vectors_sha256=vector_digest.hexdigest()),
                   parameter_set=params,routed=True,per_seed=list(normalized),**aggregate,
                   setup_worst_slack_ns=min(r['setup_worst_slack_ns'] for r in normalized),hold_worst_slack_ns=min(r['hold_worst_slack_ns'] for r in normalized),drc_violations=0)
    if not ppa_provenance_valid('T10',reference,reference):
        raise ValueError('normalized scoring record fails scope/parameter provenance')
    outputs={output:json.dumps(evidence,indent=2)+'\n',output.with_name('scoring_reference.json'):json.dumps(reference,indent=2)+'\n',
             output.with_name('evaluator_inventory.json'):inventory_text}
    if any(path.exists() for path in outputs):
        raise ValueError('output already exists; do not overwrite audited evidence')
    output.parent.mkdir(parents=True,exist_ok=True)
    for path,text in outputs.items():
        path.write_text(text)
    print('PASS complete three-seed audit; generated evidence only, authoritative baselines not edited')


if __name__=='__main__':
    main()
