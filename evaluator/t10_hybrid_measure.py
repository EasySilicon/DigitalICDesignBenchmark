#!/usr/bin/env python3
"""Measure explicit archived T10 candidates under the v16 hybrid policy.

Jobs name external, source-bound input records. Completed old measurements may
be reused after identity checks; failed native stages are retained, not retried
or converted into favorable scores. No model names or local paths are built in.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback

from t10_hybrid_ppa import (REPO, aggregate, artifact, check, external_directory,
                            functional_qualified, policy, score, source_hash, write)
from t10_candidate_physical import active_records
from t10_candidate_power import brace, validate_paths
from grade_t10_candidate_ppa import drc_count
from public_check import sources_from_filelist

BACKEND = REPO / 'evaluator/t10_backend/hybrid'


def native(script, output, *, env=None, timeout=900):
    path = output.with_suffix('.tcl')
    path.write_text(script)
    with output.open('x') as log:
        subprocess.run(['openroad', '-exit', '-no_init', str(path)],
                       stdout=log, stderr=subprocess.STDOUT, check=True,
                       timeout=timeout, env=env)
    report = output.read_text()
    if '[ERROR' in report:
        raise ValueError('native analysis error: ' + str(output))
    return report


def timed_tcl(stage, script):
    """Flush stage boundaries so an interrupted native run remains attributable."""
    return (f'puts "T10_STAGE_BEGIN {stage} [clock milliseconds]"\nflush stdout\n'
            'set t10_stage_start [clock milliseconds]\n' + script + '\n'
            f'puts "T10_STAGE_END {stage} [expr {{[clock milliseconds] - $t10_stage_start}}]"\n'
            'flush stdout\n')


def libraries(corner):
    libs = sorted(p for p in (REPO / 'vendor/asap7/lib/NLDM').glob('*RVT_' + corner + '_nldm_*')
                  if 'FAKE' not in p.name)
    if len(libs) != 5:
        raise ValueError('five standard-cell libraries required')
    return libs


def map_periphery(model, source, out, orfs, seed=11):
    """Map a fresh peripheral shell when there is no qualified old cache."""
    from slang_frontend import executable
    from t10_power_with_slang import normalize_blackbox_parameters
    from t10_structure_check import MAX_NON_PE_STATE_BITS
    from t10_candidate_power import shell_target
    ip, _ = active_records(model / f'seed{seed}')
    inputs = json.loads(ip.read_text())
    pe = inputs['pe_module']
    variant = inputs['variant'] + '_power_shell_area'
    config = out / 'peripheral_mapping.mk'
    fields = dict(PLATFORM='asap7', DESIGN_NAME='npu_systolic_matmul_16x16',
                  VERILOG_FILES=' '.join(map(str, sources_from_filelist(model / 'submission'))),
                  SDC_FILE=str(REPO / 'evaluator/t10_backend/v1/power_gate.sdc'),
                  CORE_UTILIZATION=24, PLACE_DENSITY=.24, SYNTH_USE_SYN=0,
                  SYNTH_HIERARCHICAL=0, CORNER='WC', SYNTH_BLACKBOXES=pe, ABC_AREA=1,
                  SYNTH_HDL_FRONTEND='slang', SYNTH_MEMORY_MAX_BITS=MAX_NON_PE_STATE_BITS)
    config.write_text(''.join(f'export {k} = {v}\n' for k, v in fields.items()))
    command = ['make', '-C', str(Path(orfs) / 'flow'), f'DESIGN_CONFIG={config}',
               f'FLOW_VARIANT={variant}', f'PLATFORM_DIR={REPO / "vendor/asap7"}',
               'LIB_MODEL=NLDM', 'ASAP7_USE_VT=RVT', f'YOSYS_EXE={executable()}',
               f'OPENROAD_EXE={shutil.which("openroad")}', 'NUM_CORES=4', shell_target(variant)]
    with (out / 'peripheral_mapping.log').open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=7200)
    original = Path(orfs) / 'flow' / shell_target(variant)
    rtl = '\n'.join(p.read_text() for p in sources_from_filelist(model / 'submission'))
    rtl = re.sub(r'/\*.*?\*/|//[^\n]*', '', rtl, flags=re.S)
    module = re.search(r'\bmodule\s+' + re.escape(pe) + r'\b.*?\bendmodule\b', rtl, re.S)
    if module is None:
        raise ValueError('original source PE definition not found')
    mapped, adapter = normalize_blackbox_parameters(original.read_text(), pe, module[0])
    validate_paths(mapped, pe)
    shell = out / 'mapped_periphery.v'
    shell.write_text(mapped)
    proof = out / 'mapped_periphery_proof.json'
    write(proof, dict(candidate_source_sha256=source, cached_shell=artifact(shell),
                      original_mapped_shell=artifact(original), mapping_config=artifact(config),
                      physical_input=artifact(ip), blackbox_adapter=adapter))
    return artifact(shell), artifact(proof)


def characterize(model, seed, out, source):
    """Read this seed's extracted PE and restrict timing to register paths."""
    inputs_path, physical_path = active_records(model / f'seed{seed}')
    inputs = json.loads(inputs_path.read_text())
    physical = json.loads(physical_path.read_text())
    if (inputs['source_sha256'] != source or inputs['layout_seed'] != seed
            or physical['inputs_sha256'] != artifact(inputs_path)['sha256']
            or physical['exit_code'] != 0):
        raise ValueError('incomplete or mismatched physical measurement')
    if 'hierarchy' in physical:
        raise ValueError('hierarchical PE needs explicit bottom-up characterization')
    for record in physical['artifacts'].values():
        check(record)
    out.mkdir(parents=True, exist_ok=False)
    views = physical['artifacts']
    models = {}
    for corner in ('SS', 'TT'):
        models[corner] = out / (corner + '.lib')
        script = 'set_thread_count 4\n'
        script += timed_tcl('libraries', ''.join('read_liberty ' + brace(p) + '\n'
                                                for p in libraries(corner)))
        for cmd, ext in [('db', 'odb'), ('sdc', 'sdc'), ('spef', 'spef')]:
            script += timed_tcl('read_' + cmd, 'read_' + cmd + ' ' + brace(views['6_final.' + ext]['path']))
        script += 'set_propagated_clock [all_clocks]\nset_clock_latency -source 0 [all_clocks]\n'
        script += timed_tcl('write_timing_model', 'write_timing_model ' + brace(models[corner]))
        if corner == 'SS':
            script += '''set_cmd_units -time ns
foreach kind {max min} {
    set paths [find_timing_paths -from [all_registers -clock_pins] -to [all_registers -data_pins] -path_delay $kind -sort_by_slack -group_path_count 1]
    if {![llength $paths]} {error "missing PE-internal register path"}
    puts "T10_PE_INTERNAL $kind [get_property [lindex $paths 0] slack]"
}
'''
            script += 'write_abstract_lef ' + brace(out / 'pe.lef') + '\n'
            script += 'source ' + brace(BACKEND / 'pe_geometry.tcl') + '\n'
        script += 'exit\n'
        # This is evaluator model extraction, not candidate compilation. Large
        # input cones require repeated STA searches for every boundary input.
        # Keep the worker watchdog, rather than an unrelated 15-minute cutoff.
        report = native(script, out / (corner + '.log'), timeout=None,
                        env=os.environ | {'T10_GEOMETRY': str(out / 'geometry.json')})
        if corner == 'SS':
            timing = {k: float(v) for k, v in re.findall(r'^T10_PE_INTERNAL (max|min) (\S+)$', report, re.M)}
    geometry = json.loads((out / 'geometry.json').read_text())
    if geometry['internal_macro_area_um2'] != 0:
        raise ValueError('unexpected unresolved internal PE macro')
    # Route DRC reports must come from this checkpoint's result hierarchy.
    routed = Path(views['6_final.odb']['path'])
    parts = list(routed.parts)
    if parts.count('results') != 1:
        raise ValueError('cannot bind route DRC to the selected checkpoint')
    parts[parts.index('results')] = 'reports'
    drc = Path(*parts).parent / '5_route_drc.rpt'
    return dict(source_sha256=source, layout_seed=seed, pe_master=inputs['pe_module'],
                pe_cell_area_um2=geometry['cell_area_um2'], timing_ns=timing,
                drc_violations=drc_count(drc.read_text()), route_drc=artifact(drc),
                models={c: artifact(p) for c, p in models.items()}, prepared=str(out),
                physical=artifact(physical_path), inputs=artifact(inputs_path), views=views)


def verified_power(path, source, seed, physical):
    data = json.loads(Path(path).read_text())
    if (data['source_sha256'] != source or data['layout_seed'] != seed
            or data['physical_inputs'] != physical['views']
            or data['numerical_oracle_passed'] is not True
            or data['protocol_and_latency_passed'] is not True
            or data['matrix_blocks'] != 200 or data['output_points_checked'] != 51200
            or min(data['activity_annotation_fraction'], data['sequential_activity_annotation_fraction']) < .95):
        raise ValueError('PE power is not qualified for this source/seed')
    for key in ('raw_activity', 'averaged_activity', 'merge_audit', 'power_report',
                'workload_manifest', 'power_compile_record'):
        if key in data:
            check(data[key])
    for record in data['netlists']:
        check(record)
    for filename, digest in data['tt_standard_libraries'].items():
        if artifact(REPO / 'vendor/asap7/lib/NLDM' / Path(filename).name)['sha256'] != digest:
            raise ValueError('PE power library changed')
    frozen = json.loads((REPO / 'benchmark/ppa-baselines.json').read_text())['tasks']['T10']
    if data['workload_manifest']['sha256'] != frozen['workload_sha256']:
        raise ValueError('gate workload differs from the fixed power contract')
    return data


def graph(binding, out):
    target = out / 'graph'
    target.mkdir()
    quote = lambda p: '"' + str(p).replace('\\', '\\\\').replace('"', '\\"') + '"'
    text = ''.join('read_liberty -lib ' + quote(p) + '\n'
                   for p in [*libraries('SS'), Path(binding['SS_model']['path'])])
    text += 'read_verilog ' + quote(binding['shell']['path']) + '\n'
    text += 'hierarchy -check -top npu_systolic_matmul_16x16\n'
    text += 'setattr -mod -unset keep_hierarchy\nsetattr -unset keep_hierarchy\nflatten -noscopeinfo\n'
    text += 'write_json ' + quote(target / 'mapped.json') + '\n'
    (target / 'flatten.ys').write_text(text)
    with (target / 'yosys.log').open('x') as log:
        subprocess.run(['yosys', '-T', '-s', str(target / 'flatten.ys')],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
    write(target / 'producer.json', dict(source_sha256=binding['source_sha256'],
                                       shell=binding['shell'], script=artifact(target / 'flatten.ys')))
    write(out / 'graph_input.json', dict(source_sha256=binding['source_sha256'],
                                       mapped_shell=binding['shell'], graph=artifact(target / 'mapped.json'),
                                       producer_inputs=artifact(target / 'producer.json')))


def new_activity(model, seed, source, shell, compiler, orfs, output, trace_periphery):
    """Use a fresh local model view, leaving all original trials untouched."""
    import t10_candidate_power
    if compiler:
        root = Path(compiler)
        os.environ['VERILATOR_ROOT'] = str(root)
        os.environ['PATH'] = str(root / 'bin') + os.pathsep + os.environ['PATH']
        os.environ.pop('VERILATOR_BIN', None)
        os.environ.pop('VERILATOR_TEST_FLAGS', None)
    os.environ['CCACHE_DISABLE'] = '1'
    os.environ['OBJCACHE'] = ''
    if not output.exists():
        output.mkdir(parents=True)
        shutil.copytree(model / 'submission/rtl', output / 'submission/rtl')
        for s in (11, 29, 47):
            target = output / f'seed{s}'
            target.mkdir()
            ip, pp = active_records(model / f'seed{s}')
            for p in [ip, pp, model / f'seed{s}/active_attempt.json']:
                if p.exists():
                    shutil.copy2(p, target / p.name)
    if source_hash(output / 'submission') != source:
        raise ValueError('local measurement copy differs from frozen source')
    t10_candidate_power.measure(output, seed, Path(orfs),
                                trace_periphery=trace_periphery, mapped_shell=shell,
                                parent_optimization='default')
    return output / f'activity_seed{seed}/power.json'


def peripheral(binding, power, out):
    """Analyze the actual full gate trace; never use vectorless activity."""
    import t10_hybrid_power
    from t10_hybrid_inputs import input_caps
    trace = out / 'peripheral_activity'
    trace.mkdir()
    # Bind the original file rather than duplicating potentially huge SAIF.
    (trace / 'activity.saif').symlink_to(Path(power['raw_activity']['path']))
    graph(binding, out)
    t10_hybrid_power.main(str(out / 'binding.json'), contract_io=True)
    return input_caps(str(out / 'binding.json'))


def cached_peripheral(path, binding):
    """Accept only the previously validated mapped-shell / zero-wire result."""
    root = Path(path)
    old_binding = json.loads((root / 'binding.json').read_text())
    if (old_binding['source_sha256'] != binding['source_sha256']
            or old_binding['shell']['sha256'] != binding['shell']['sha256']):
        raise ValueError('cached peripheral source or netlist differs')
    result_path = root / 'result.json'
    if not result_path.exists():
        result_path = root / 'estimate_contract.json'
    result = json.loads(result_path.read_text())
    # Early producers retained these ledgers as separate, bound reports.
    # Normalize their shape without editing any original evidence.
    if 'gate_qualification' not in result:
        result['gate_qualification'] = json.loads((root / 'peripheral_activity/receipt.json').read_text())
    if 'input_load_ledger' not in result:
        result['input_load_ledger'] = json.loads((root / 'input_capacitance_r3/result.json').read_text())
    gate = result['gate_qualification']
    if (gate['source_sha256'] != binding['source_sha256'] or gate['matrix_blocks'] != 200
            or gate['output_points_checked'] != 51200
            or not any(r['sha256'] == binding['shell']['sha256'] for r in gate['original_netlists'])):
        raise ValueError('cached gate evidence differs from its source/netlist/workload')
    check(result['gate_qualification']['activity'])
    check(result['gate_qualification']['workload_manifest'])
    check(result['gate_qualification']['simulation_log'])
    if (result['gate_qualification']['numerical_oracle_passed'] is not True
            or result['gate_qualification']['protocol_and_latency_passed'] is not True
            or result['activity_mapping']['missing_native_activity'] != 0
            or result['assumptions']['output_load_ff'] != 0
            or result['assumptions']['input_transition_ps'] != 0):
        raise ValueError('cached peripheral gate/activity qualification failed')
    for record in result['old_pe_report_bindings']:
        check(record)
    row = next(r for r in result['sensitivities'] if r['assumed_wire_um_per_sink'] == 0)
    check(row['native_report'])
    check(result['input_load_ledger']['native_table'])
    return dict(cell_area_um2=result['peripheral_lef_cell_area_um2'],
                power_w=row['shell_power_w'],
                input_power_w=result['input_load_ledger']['rows'][0]['primary_input_capacitor_charging_w'],
                duration_seconds=result['duration_seconds'], annotation_fraction=1.0,
                evidence=artifact(result_path))


def measure(job, out, compiler, orfs):
    model = Path(job['model_dir'])
    source = source_hash(model / 'submission')
    if source != job['source_sha256']:
        raise ValueError('candidate source identity mismatch')
    check(job['functional_report'])
    report = json.loads(Path(job['functional_report']['path']).read_text())
    if not functional_qualified(report):
        raise ValueError('strict functional acceptance is not complete')
    physical_records = []
    seeds = []
    for seed in (11, 29, 47):
        _, pp = active_records(model / f'seed{seed}')
        physical = json.loads(pp.read_text())
        if physical['exit_code'] == 0:
            seeds.append(seed)
        elif physical['exit_code'] != 124:
            raise ValueError('physical tool error requires attribution before scoring')
        budget = model / f'seed{seed}/physical_budget.json'
        if budget.exists():
            physical_records.append(json.loads(budget.read_text()))
    if len(seeds) != 3:
        from physical_budget import validate_records
        timeouts = validate_records(physical_records, source, 'T10')
        if set(seeds) != {11, 29, 47} - timeouts:
            raise ValueError('physical failures lack matching timeout receipts')
        if not seeds:
            raise ValueError('all physical seeds timed out; no measured PPA is available')
    else:
        # Legacy successful routes may predate the current receipt policy.
        physical_records = []
    anchor_seed = seeds[0]
    if not job.get('shell'):
        job = dict(job)
        job['shell'], job['shell_proof'] = map_periphery(model, source, out, orfs, anchor_seed)
    check(job['shell'])
    shell = Path(job['shell']['path'])
    check(job['shell_proof'])
    proof = json.loads(Path(job['shell_proof']['path']).read_text())
    if proof.get('candidate_source_sha256', proof.get('source_sha256')) != source:
        raise ValueError('mapped shell proof does not bind the candidate source')
    proof_shell = proof.get('cached_shell', proof.get('shell'))
    if proof_shell is None or proof_shell['sha256'] != job['shell']['sha256']:
        raise ValueError('mapped shell differs from its source proof')
    rows = []
    shell_cost = None
    for seed in seeds:
        seed_dir = out / f'seed{seed}'
        marker = seed_dir / 'row.json'
        if marker.exists():
            # Resume requires the same original physical and power identities.
            row = json.loads(marker.read_text())
            for record in row['evidence'].values():
                check(record)
            rows.append(row)
            continue
        pe = characterize(model, seed, seed_dir, source)
        paths = sorted(validate_paths(shell.read_text(), pe['pe_master']))
        old = job.get('power_records', {}).get(str(seed))
        if old:
            check(old)
            power_path = Path(old['path'])
        else:
            power_path = new_activity(model, seed, source, shell, compiler, orfs,
                                      out / 'gate', trace_periphery=(seed == anchor_seed))
        power = verified_power(power_path, source, seed, pe)
        binding = dict(label=job['label'], source_sha256=source, layout_seed=seed,
                       prepared=pe['prepared'], pe_master=pe['pe_master'], pe_count=256,
                       pe_paths=paths, shell=job['shell'],
                       SS_model=pe['models']['SS'], TT_model=pe['models']['TT'],
                       old_power=artifact(power_path),
                       limitations=['PE-internal extracted timing only; no top-level timing score',
                                    'mapped peripheral power excludes global CTS, wires and delay glitches'])
        if seed == anchor_seed:
            write(out / 'binding.json', binding)
            if job.get('peripheral_cache'):
                shell_cost = cached_peripheral(job['peripheral_cache'], binding)
            else:
                if not power.get('peripheral_activity_traced'):
                    raise ValueError('no peripheral activity in the gate trace')
                ports = peripheral(binding, power, out)
                estimate = json.loads((out / 'estimate_contract.json').read_text())
                shell_cost = dict(cell_area_um2=estimate['peripheral_lef_cell_area_um2'],
                                  power_w=estimate['sensitivities'][0]['shell_power_w'],
                                  input_power_w=ports['rows'][0]['primary_input_capacitor_charging_w'],
                                  duration_seconds=estimate['duration_seconds'],
                                  annotation_fraction=estimate['peripheral_activity_import']['sequential_pins_annotated'] /
                                      estimate['peripheral_activity_import']['sequential_pins_total'],
                                  evidence=artifact(out / 'estimate_contract.json'))
            write(out / 'peripheral_cost.json', shell_cost)
        if shell_cost is None:
            shell_cost = json.loads((out / 'peripheral_cost.json').read_text())
        check(shell_cost['evidence'])
        if abs(power['vcd_window_seconds'] - shell_cost['duration_seconds']) > 1e-15:
            raise ValueError('PE and peripheral power windows differ')
        # For flat PE reports the macro category is empty, so full native
        # power is the complete PE cost. Parent power includes PE output loads.
        from t10_hybrid_power import accounted
        pe_power = accounted(Path(power['power_report']['path']).read_text())
        watts = shell_cost['power_w'] + 256 * pe_power + shell_cost['input_power_w']
        row = dict(layout_seed=seed, source_sha256=source, policy_id=policy()['policy_id'],
                   timing_scope=policy()['timing_scope'], pe_routed=True, matrix_blocks=200,
                   pe_cell_area_um2=pe['pe_cell_area_um2'], peripheral_cell_area_um2=shell_cost['cell_area_um2'],
                   area_um2=shell_cost['cell_area_um2'] + 256 * pe['pe_cell_area_um2'],
                   pe_power_w=pe_power, peripheral_power_w=shell_cost['power_w'],
                   primary_input_power_w=shell_cost['input_power_w'], average_power_mw=watts * 1000,
                   duration_seconds=power['vcd_window_seconds'],
                   energy_per_op_pj=watts * power['vcd_window_seconds'] / 200 * 1e12,
                   setup_worst_slack_ns=pe['timing_ns']['max'], hold_worst_slack_ns=pe['timing_ns']['min'],
                   delay_ns=1 - pe['timing_ns']['max'], drc_violations=pe['drc_violations'],
                   annotation_fraction=min(power['activity_annotation_fraction'], power['sequential_activity_annotation_fraction']),
                   peripheral_annotation_fraction=shell_cost['annotation_fraction'],
                   evidence=dict(physical=pe['physical'], inputs=pe['inputs'], power=artifact(power_path),
                                 pe_timing=artifact(seed_dir / 'SS.log'), peripheral=shell_cost['evidence']))
        write(marker, row)
        rows.append(row)
    if source_hash(model / 'submission') != source:
        raise ValueError('frozen candidate changed during measurement')
    result = aggregate(source, rows, physical_records)
    result['label'] = job['label']
    result['functional_report'] = job['functional_report']
    write(out / 'measurement.json', result)
    return result


def campaign(config):
    from t10_hybrid_scheduler import run
    return run(config)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    args = parser.parse_args()
    campaign(json.loads(args.campaign.read_text()))
