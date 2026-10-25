#!/usr/bin/env python3
"""Measure archived candidates' own PEs; never edit RTL or invent power scores.

This is the physical phase only. A completed flow still requires connectivity,
native geometry, extracted timing, and full-DUT activity/power qualification.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from public_check import sources_from_filelist
from ppa_aggregate import source_hash
from t10_structure_with_slang import inspect
from physical_budget import run as physical_run, timed_out as physical_timed_out

REPO=Path(__file__).resolve().parents[1]
TRIALS={
    'gpt-6-astra':'gpt6astra_noskills_from_t04_v6_20261003',
    'gpt-6-sol':'gpt6sol_noskills_from_t04_v6_20261003',
    'gpt-6.1-sol':'gpt61sol_20261003',
}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024**2),b''):h.update(chunk)
    return h.hexdigest()


def artifact(path):
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))


def write_new_or_same(path,text):
    if path.exists():
        if path.read_text()!=text:raise ValueError('changed inputs: '+str(path))
    else:path.write_text(text)


def prepare(model,trials,work):
    original=trials/TRIALS[model]/'workspaces/T10'
    archive=trials/'rtl_retention_20261009_222440'/TRIALS[model]/'workspaces/T10'
    digest=source_hash(original)
    if digest!=source_hash(archive):raise ValueError('archive/source mismatch: '+model)
    directory=work/model;directory.mkdir(parents=True,exist_ok=True)
    snapshot=directory/'submission'
    if not snapshot.exists():
        snapshot.mkdir();shutil.copytree(archive/'rtl',snapshot/'rtl')
    if source_hash(snapshot)!=digest:raise ValueError('snapshot/source mismatch: '+model)
    structural=directory/'structure.json'
    if not structural.exists():
        result=inspect(snapshot)
        result.update(candidate_source_sha256=digest,checker_sha256=sha(REPO/'evaluator/t10_structure_check.py'))
        structural.write_text(json.dumps(result,indent=2)+'\n')
    result=json.loads(structural.read_text())
    if result.get('candidate_source_sha256')!=digest or result.get('checker_sha256')!=sha(REPO/'evaluator/t10_structure_check.py'):
        raise ValueError('structural provenance changed: '+model)
    if not result.get('passed'):raise ValueError('structural gate failed: '+model+' '+str(result.get('reason')))
    pe=result['pe_module']
    if not pe.replace('_','').isalnum():raise ValueError('unsupported PE identifier')
    return dict(model=model,source_sha256=digest,submission=snapshot,pe=pe,structure=artifact(structural))


def active_records(directory):
    pointer=directory/'active_attempt.json'
    if pointer.exists():
        selected=json.loads(pointer.read_text())
        if selected!={'inputs':'inputs40.json','physical':'baseline40.json'}:
            raise ValueError('unknown active measurement attempt')
        return directory/selected['inputs'],directory/selected['physical']
    return directory/'inputs.json',directory/'baseline.json'


def run_seed(item,seed,work,orfs,target,*,memory_gib=40,allow_swap=False,prepare_only=False):
    model=item['model'];pe=item['pe'];directory=work/model/f'seed{seed}'
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        sdc=directory/'constraint.sdc';hook=directory/'clock_layers.tcl';config=directory/'config.mk'
        write_new_or_same(sdc,'\n'.join([
            f'current_design {pe}',
            'create_clock -name clk_clock -period 1000 [get_ports clk]',
            'create_clock -name vclk_in -period 1000',
            'create_clock -name vclk_out -period 1000',
            'set_clock_latency -source 600 [get_clocks vclk_out]',
            'set_input_delay 200 -clock vclk_in [all_inputs -no_clocks]',
            'set_output_delay 200 -clock vclk_out [all_outputs]',
            'set_false_path -from [get_ports rst_n]','']))
        write_new_or_same(hook,'set_routing_layers -clock M6-M7\nset_wire_rc -clock -layer M7\n')
        fields=dict(PLATFORM='asap7',DESIGN_NAME=pe,
            VERILOG_FILES=' '.join(map(str,sources_from_filelist(item['submission']))),SDC_FILE=str(sdc),
            CORE_UTILIZATION=24,CORE_ASPECT_RATIO=1,CORE_MARGIN=.5,PLACE_DENSITY=.24,
            SYNTH_USE_SYN=0,SYNTH_HIERARCHICAL=0,CORNER='WC',GPL_ROUTABILITY_DRIVEN=0,
            DETAIL_PLACEMENT_ARGS='-max_displacement 100',MAX_ROUTING_LAYER='M7',MIN_CLK_ROUTING_LAYER='M6',
            ROUTING_LAYER_ADJUSTMENT=0,HOLD_SLACK_MARGIN=75,SETUP_SLACK_MARGIN=175,
            SKIP_INCREMENTAL_REPAIR=0,CTS_CLUSTER_SIZE=64,CTS_CLUSTER_DIAMETER=100,
            CTS_ARGS='-sink_clustering_enable -repair_clock_nets -sink_clustering_size 64 -sink_clustering_max_diameter 100 -no_insertion_delay',
            SKIP_CTS_REPAIR_TIMING=0,PRE_CTS_TCL=str(hook),GRT_SEED=seed,OR_SEED=seed,
            DETAILED_ROUTE_END_ITERATION=20)
        write_new_or_same(config,''.join(f'export {key} = {value}\n' for key,value in fields.items()))
        variant=f'ic_t10_candidate_{model.replace("-","_").replace(".","_")}_{item["source_sha256"][:10]}_s{seed}'
        inputs=dict(model=model,source_sha256=item['source_sha256'],structure=item['structure'],pe_module=pe,
            layout_seed=seed,measurement_scope='single_pe',config=artifact(config),sdc=artifact(sdc),clock_hook=artifact(hook),
            orfs_revision=subprocess.check_output(['git','-C',str(orfs),'rev-parse','HEAD'],text=True).strip(),
            openroad=subprocess.check_output(['openroad','-version'],text=True).strip(),
            yosys=subprocess.check_output(['yosys','-V'],text=True).strip(),variant=variant,
            memory_max_bytes=memory_gib*1024**3,memory_swap_max_bytes=None if allow_swap else 0,threads=4)
        suffix='40' if memory_gib==40 else ''
        if memory_gib not in (32,40):raise ValueError('unsupported memory policy')
        input_path=directory/f'inputs{suffix}.json'
        write_new_or_same(input_path,json.dumps(inputs,indent=2)+'\n')
        marker=directory/f'{target}{suffix}.json'
        if marker.exists():
            previous=json.loads(marker.read_text())
            if previous['exit_code']!=0:raise ValueError('previous failure needs attribution; not automatically retrying')
            for record in previous['artifacts'].values():
                path=Path(record['path'])
                if not path.is_file() or artifact(path)!=record:raise ValueError('completed artifact changed')
            return previous
        command=['systemd-run','--user','--scope',f'--unit={variant}-{target}{suffix}',
            '-p',f'MemoryMax={memory_gib}G','-p','MemorySwapMax=infinity' if allow_swap else 'MemorySwapMax=0','-p','CPUQuota=400%',
            'make','-C',str(orfs/'flow'),f'DESIGN_CONFIG={config}',f'FLOW_VARIANT={variant}',
            f'PLATFORM_DIR={REPO/"vendor/asap7"}','LIB_MODEL=NLDM','ASAP7_USE_VT=RVT',
            f'OPENROAD_EXE={shutil.which("openroad")}',f'YOSYS_EXE={shutil.which("yosys")}','NUM_CORES=4',
            *(['route','do-finish'] if target=='baseline' else [target])]
        if prepare_only:
            return dict(command=command,inputs=inputs,input_path=str(input_path),marker=str(marker))
        if memory_gib==40 and target=='baseline':
            raise ValueError('40 GiB baseline attempts must use the monitored serial coordinator')
        env=dict(os.environ,MALLOC_ARENA_MAX='2');started=time.time()
        print('START',model,seed,target,flush=True)
        with (directory/f'{target}{suffix}.log').open('x') as log:
            result=physical_run(command,env=env,stdout=log,stderr=subprocess.STDOUT,
                task='T10',source=item['source_sha256'],seed=seed,record_path=directory/'physical_budget.json')
        result_dir=orfs/'flow/results/asap7'/pe/variant
        paths=([result_dir/f'6_final.{ext}' for ext in ('odb','spef','sdc','v')] if target=='baseline' else
               [result_dir/'1_2_yosys.v'])
        record=dict(status='physical_flow_completed_not_qualified' if result.returncode==0 else 'failed_pending_attribution',
            model=model,layout_seed=seed,exit_code=result.returncode,elapsed_seconds=time.time()-started,
            inputs_sha256=sha(input_path),artifacts={p.name:artifact(p) for p in paths if p.is_file()})
        if result.returncode==0 and len(record['artifacts'])!=len(paths):raise ValueError('flow returned without complete outputs')
        marker.write_text(json.dumps(record,indent=2)+'\n')
        print('FINISH',model,seed,record['status'],flush=True)
        return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trials-root',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--orfs',type=Path,required=True);p.add_argument('--models',choices=TRIALS,nargs='+',default=list(TRIALS))
    p.add_argument('--seeds',type=int,choices=(11,29,47),nargs='+',default=[11,29,47])
    p.add_argument('--target',choices=('synth','baseline'),default='baseline')
    a=p.parse_args();work=a.work.resolve();orfs=a.orfs.resolve()
    # Current 40-GiB flows run serially; 32-GiB inputs remain historical records.
    items=[prepare(m,a.trials_root.resolve(),work) for m in a.models]
    rows=[]
    for seed in a.seeds:
        for item in items:
            if a.target=='baseline':
                from run_t10_candidate_40g import completed_physical
                from t10_physical_with_slang import physical
                directory=work/item['model']/f'seed{seed}'
                if physical_timed_out(directory):
                    row=json.loads((directory/'baseline40.json').read_text())
                elif completed_physical(directory):
                    row=json.loads((directory/'baseline40.json').read_text())
                else:
                    row,_=physical(item,seed,work,orfs)
            else:
                row=run_seed(item,seed,work,orfs,a.target)
            rows.append(row)
    (work/f'{a.target}_summary.json').write_text(json.dumps(rows,indent=2)+'\n')


if __name__=='__main__':main()
