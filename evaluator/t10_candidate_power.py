#!/usr/bin/env python3
"""Full gate-DUT activity and complete flat-PE power for an archived candidate.

Consumes an unchanged, completed candidate route. Never substitutes reference
PEs, RTL activity, vectorless estimates, or incomplete physical checkpoints.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import resource

from t10_candidate_physical import REPO, artifact, sha, write_new_or_same, active_records
from public_check import sources_from_filelist
from ppa_aggregate import source_hash
from ppa_power_probe import instrument_testbench, check_t10_workload, useful_operations
from make_t10_power_vectors import create

BACKEND=REPO/'evaluator/t10_backend/v1'
sys.path.insert(0,str(BACKEND))
from run_gate_activity import hierblock, primitive_trace_off, shell_trace_off
from staged_gate_build import build as staged_build
from saif_window import build as window_build
from merge_pe_saif import instances, normalized, merge
from saif_activity import export_scope, TCL as ACTIVITY_TCL
from measure_power import brace


def run(command,log,cwd):
    # RAM is bounded by the encompassing cgroup, not RLIMIT_AS.
    resource.setrlimit(resource.RLIMIT_AS,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))
    started=time.monotonic()
    print('RUN',log,flush=True)
    with log.open('w') as stream:
        subprocess.run(command,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,check=True)
    return time.monotonic()-started


def run_unoptimized_periphery(command,log,cwd):
    """Bound frontend optimization cost for a large mapped shell.

    Only the unmeasured parent changes optimization level; its actual mapped
    source, child DPI hash guards, measured PE model, and acceptance stay intact.
    The staged builder hashes this amended argument file after the native run.
    See https://verilator.org/guide/latest/exe_verilator.html#cmdoption-O0.
    """
    if log.name=='actual_npu_systolic_matmul_16x16.log':
        expected=log.parent/'build/Vnpu_systolic_matmul_16x16__hierMkArgs.f'
        if len(command)!=3 or command[1]!='-f' or Path(command[2]).resolve()!=expected.resolve():
            raise ValueError('unexpected peripheral frontend command; measured PE must not be modified')
        arguments=expected.read_text()
        if '--top-module-encoded npu_systolic_matmul_16x16' not in arguments:
            raise ValueError('frontend argument file does not name the unmeasured parent')
        if '-O0' not in arguments.split():expected.write_text(arguments+'\n-O0\n')
    return run(command,log,cwd)


def validate_paths(shell,pe):
    # Tile wrappers may remain hierarchical; count elaborated instances, not
    # occurrences in a module definition (16 tiles x 16 PEs is still 256).
    modules={match[1]:match[2] for match in re.finditer(
        r'\bmodule\s+([^\s(;]+).*?;(.*?)\bendmodule\b',shell,re.S)}
    paths=[]
    def visit(master,prefix,parents):
        if master in parents:raise ValueError('recursive mapped shell hierarchy')
        for child,name in instances(modules[master],{*modules,pe}):
            path=[*prefix,normalized(name)]
            if child==pe:paths.append('.'.join(path))
            else:visit(child,path,parents|{master})
    if 'npu_systolic_matmul_16x16' not in modules:
        raise ValueError('mapped full DUT must contain 256 distinct candidate PEs')
    visit('npu_systolic_matmul_16x16',[],set())
    if len(paths)!=256 or len(set(paths))!=256:raise ValueError('mapped full DUT must contain 256 distinct candidate PEs')
    return set(paths)


def shell_target(variant):
    # Request just the mapped Verilog. The aggregate `synth` target also
    # constructs an ODB, which cannot link these intentional PE black boxes.
    return f'results/asap7/npu_systolic_matmul_16x16/{variant}/1_2_yosys.v'


def qualified_shell(model_dir,seed,inputs):
    """Only reuse this candidate's shell after a complete seed-11 gate run.

    The shell has no layout-dependent cells: each simulation still fills its
    black boxes with that seed's own final PE netlist and checks all outputs.
    """
    proof=model_dir/'activity_seed11/power.json'
    if seed==11 or not proof.exists():return None
    measured=json.loads(proof.read_text())
    if measured.get('status')!='candidate_single_seed_activity_power_measured' or \
            measured.get('source_sha256')!=inputs['source_sha256'] or \
            measured.get('numerical_oracle_passed') is not True or \
            measured.get('protocol_and_latency_passed') is not True or \
            measured.get('matrix_blocks')!=200 or measured.get('output_points_checked')!=51200:
        raise ValueError('cached shell does not have matching full-DUT qualification')
    entry=measured['netlists'][0];path=Path(entry['path'])
    if artifact(path)!=entry:raise ValueError('qualified shell netlist changed')
    return path


def annotation(report):
    counts=re.findall(r'^input\s+(\d+)\s+unannotated\s+(\d+)',report,re.M)
    sequential=re.search(r'T10_SEQUENTIAL_ACTIVITY annotated=(\d+) total=(\d+)',report)
    if not counts or not sequential or int(sequential[2])==0:raise ValueError('missing activity coverage')
    fraction=min(int(a)/(int(a)+int(b)) if int(a)+int(b) else 0 for a,b in counts)
    seq=int(sequential[1])/int(sequential[2])
    if min(fraction,seq)<.95:raise ValueError('activity annotation below 95%')
    return fraction,seq


def check_connectivity(odb,output,log):
    # OpenDB's Python bindings belong to OpenROAD's embedded interpreter.
    # They are intentionally not a dependency of the system Python environment.
    run(['openroad','-exit','-no_init','-python',str(BACKEND/'check_connectivity_full.py'),
         str(odb),str(output)],log,REPO)


def measure(model_dir,seed,orfs):
    directory=model_dir/f'seed{seed}'
    input_path,physical_path=active_records(directory)
    physical=json.loads(physical_path.read_text())
    inputs=json.loads(input_path.read_text())
    if physical['exit_code'] or physical['inputs_sha256']!=sha(input_path):
        raise ValueError('physical flow not complete or inputs changed')
    for entry in physical['artifacts'].values():
        if artifact(Path(entry['path']))!=entry:raise ValueError('physical artifact changed')
    submission=model_dir/'submission'
    if source_hash(submission)!=inputs['source_sha256']:raise ValueError('candidate RTL changed')
    pe=inputs['pe_module'];out=model_dir/f'activity_seed{seed}';out.mkdir(exist_ok=True)
    if (out/'power.json').exists():raise ValueError('power record already exists; do not overwrite')
    odb=Path(physical['artifacts']['6_final.odb']['path']);results=odb.parent
    connectivity=out/'connectivity.json'
    if not connectivity.exists():
        check_connectivity(odb,connectivity,out/'connectivity.log')
    connected=json.loads(connectivity.read_text())
    if connected['status']!='passed' or connected['odb']['sha256']!=sha(odb):raise ValueError('physical connectivity fails')
    # Map only the full-DUT shell. The 256 identical black boxes below are
    # filled by this seed's real mapped PE before any simulation is built.
    variant=inputs['variant']+'_power_shell_area'
    config=out/'shell_area.mk'
    fields=dict(PLATFORM='asap7',DESIGN_NAME='npu_systolic_matmul_16x16',
        VERILOG_FILES=' '.join(map(str,sources_from_filelist(submission))),
        SDC_FILE=str(BACKEND/'power_gate.sdc'),CORE_UTILIZATION=24,PLACE_DENSITY=.24,
        SYNTH_USE_SYN=0,SYNTH_HIERARCHICAL=0,CORNER='WC',SYNTH_BLACKBOXES=pe,ABC_AREA=1)
    write_new_or_same(config,''.join(f'export {k} = {v}\n' for k,v in fields.items()))
    shell=qualified_shell(model_dir,seed,inputs)
    if shell is None:
        run(['make','-C',str(orfs/'flow'),f'DESIGN_CONFIG={config}',f'FLOW_VARIANT={variant}',
             f'PLATFORM_DIR={REPO/"vendor/asap7"}','LIB_MODEL=NLDM','ASAP7_USE_VT=RVT',
             f'YOSYS_EXE={shutil.which("yosys")}',f'OPENROAD_EXE={shutil.which("openroad")}','NUM_CORES=4',shell_target(variant)],out/'shell_synth.log',REPO)
        shell=orfs/'flow'/shell_target(variant)
    else:
        write_new_or_same(out/'shell_reuse.json',json.dumps(dict(shell=artifact(shell),
            full_gate_qualification=artifact(model_dir/'activity_seed11/power.json'),
            same_candidate_source_sha256=inputs['source_sha256'],
            note='only the peripheral shell is reused; routed PE and full simulation remain seed-specific'),indent=2)+'\n')
    # This changes simulator compilation only, never the mapped hardware.
    # Every seed must still pass the complete real gate-DUT qualification.
    large_shell_frontend=shell.stat().st_size>=128*1024**2
    original_pe=Path(physical['artifacts']['6_final.v']['path'])
    if len(re.findall(r'\bmodule\s',original_pe.read_text()))!=1:
        raise ValueError('candidate PE must be fully mapped with no unresolved internal macros')
    paths=validate_paths(shell.read_text(),pe)
    sources=[]
    for label,path in [('shell',shell),('pe',original_pe)]:
        source=path.read_text()
        if label=='shell':source=shell_trace_off(source)
        target=out/(label+'.v');target.write_text(hierblock(source));sources.append(target)
    vectors=model_dir/'workload'
    if not (vectors/'manifest.json').exists():create(vectors)
    top=instrument_testbench('T10',REPO/'evaluator/hidden/tb_hidden_T10_stream.sv',out/'tb_power.sv')
    cells=sorted(p for p in (REPO/'vendor/asap7/verilog/stdcell').glob('asap7sc7p5t_*RVT_TT_*.v') if '_SEQ_' not in p.name)
    libraries=[]
    for source in [REPO/'env/asap7_seq_sim.v',*cells]:
        target=out/('direct_'+source.name);target.write_text(primitive_trace_off(source.read_text()));libraries.append(target)
    command=['verilator','--binary','--hierarchical','--timing','--assert','--trace-saif','--trace-underscore',
        '--trace-max-width','262144','--output-split','10000','--output-split-cfuncs','10000',
        '-Wno-fatal','-Wno-SPECIFYIGN','-j','4','--top-module',top,'--Mdir',str(out/'build'),
        str(out/'tb_power.sv'),*map(str,sources),*map(str,libraries)]
    staged_build(command,sources,out/'tb_power.sv',out,
        run_unoptimized_periphery if large_shell_frontend else run,REPO)
    executable,writer=window_build(out,top,run,REPO)
    run([str(executable),f'+POWER_VCD={out/"activity.saif"}',f'+VECTORS={vectors}','+CASE_COUNT=200'],out/'simulation.log',REPO)
    simulation=(out/'simulation.log').read_text()
    check_t10_workload(simulation,vectors,200)
    if useful_operations('T10',simulation)!=200:raise ValueError('gate workload operation count is not 200')
    audit=merge(out/'activity.saif',paths,{},out/'average.saif')
    if audit['pe_instances']!=256 or audit['timescale']!='1ps':raise ValueError('incomplete PE activity')
    duration=audit['duration_per_instance_ticks']*1e-12;clock=audit['clock_activity']
    if not clock or abs(clock[2]/(duration*256)-2e9)>2/duration:raise ValueError('activity clock is not 1 GHz')
    (out/'merge_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    mapping=export_scope(out/'average.saif',['pe'],out/'activity_nets.tsv')
    platform=REPO/'vendor/asap7/lib/NLDM'
    libs=sorted(p for p in platform.glob('asap7sc7p5t_*RVT_TT_nldm_*.lib*') if 'FAKE' not in p.name)
    if len(libs)!=5:raise ValueError('expected five TT standard-cell libraries')
    script='set_thread_count 4\n'+''.join(f'read_liberty {brace(p)}\n' for p in libs)
    script+=f'read_db {brace(odb)}\nread_sdc {brace(results/"6_final.sdc")}\nread_spef {brace(results/"6_final.spef")}\n'
    script+=f'source {brace(ACTIVITY_TCL)}\nreport_activity_annotation -report_unannotated\nreport_power -digits 9\nexit\n'
    (out/'power.tcl').write_text(script)
    with (out/'power.log').open('w') as log:
        subprocess.run(['openroad','-exit','-no_init','-no_splash',str(out/'power.tcl')],check=True,
            env=os.environ|{'T10_ACTIVITY_NETS':str(out/'activity_nets.tsv')},stdout=log,stderr=subprocess.STDOUT)
    report=(out/'power.log').read_text();fraction,seq=annotation(report)
    imported=re.search(r'T10_ACTIVITY_IMPORT nets=(\d+) pins=(\d+)',report)
    if not imported or int(imported[1])!=mapping['activity_nets']:raise ValueError('activity mapping mismatch')
    total=re.search(r'^Total\s+\S+\s+\S+\s+\S+\s+(\S+)',report,re.M)
    watts=float(total[1]) if total else 0
    if not math.isfinite(watts) or watts<=0:raise ValueError('invalid complete PE power')
    record=dict(status='candidate_single_seed_activity_power_measured',measurement_scope='single_pe',
        source_sha256=inputs['source_sha256'],layout_seed=seed,power_corner='TT',matrix_blocks=200,
        resource_policy=physical.get('resource_policy'),
        output_points_checked=51200,numerical_oracle_passed=True,protocol_and_latency_passed=True,
        total_power_w=watts,energy_j_per_block=watts*duration/200,vcd_window_seconds=duration,
        activity_annotation_fraction=fraction,sequential_activity_annotation_fraction=seq,saif_writer=writer,
        physical_inputs=physical['artifacts'],netlists=[artifact(shell),artifact(original_pe)],
        shell_mapping_policy='ASAP7 area mapping of unmeasured periphery; same-seed routed PE unchanged',
        peripheral_frontend_policy='Verilator -O0 for the >=128 MiB mapped parent only; default measured-PE optimization'
            if large_shell_frontend else 'default Verilator model optimization',
        connectivity=artifact(connectivity),merge_audit=artifact(out/'merge_audit.json'),
        staged_build_manifest=artifact(out/'staged_build_manifest.json'),simulation_log=artifact(out/'simulation.log'),
        raw_activity=artifact(out/'activity.saif'),averaged_activity=artifact(out/'average.saif'),
        workload_manifest=artifact(vectors/'manifest.json'),power_report=artifact(out/'power.log'),
        simulation_cell_models=[dict(original=artifact(source),instrumented=artifact(target))
            for source,target in zip([REPO/'env/asap7_seq_sim.v',*cells],libraries)],
        tt_standard_libraries={str(p):sha(p) for p in libs})
    (out/'power.json').write_text(json.dumps(record,indent=2)+'\n')
    print('MEASURED CANDIDATE POWER',inputs['model'],seed,watts,'W',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--seed',type=int,choices=(11,29,47),required=True)
    p.add_argument('--orfs',type=Path,required=True)
    a=p.parse_args();measure(a.model_dir.resolve(),a.seed,a.orfs.resolve())
