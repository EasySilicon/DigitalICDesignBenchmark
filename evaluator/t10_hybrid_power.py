"""Whole-design activity estimate with explicit uncalibrated wire-load sweeps."""
import json, math, re, subprocess, sys, time
from pathlib import Path
from t10_hybrid_ppa import REPO, artifact, check
from t10_candidate_power import brace

HERE=Path(__file__).resolve().parent

def native(script,log):
    with log.open('x') as stream:
        subprocess.run(['openroad','-exit','-no_init',str(script)],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=900)
    text=log.read_text()
    if '[ERROR' in text or 'T10_HYBRID_COMPLETE' not in text:raise RuntimeError('native power failed: '+str(log))
    return text

def powers(report,label):
    rows=re.findall(r'^'+label+r'\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+\S+%)?\s*$',report,re.M)
    if len(rows)!=1:raise ValueError('missing/duplicate power row '+label)
    values=list(map(float,rows[0]))
    if any(not math.isfinite(x) or x<0 for x in values) or abs(sum(values[:3])-values[3])>max(1e-18,values[3]*1e-6):raise ValueError('invalid power total')
    return values

def accounted(report):
    total=powers(report,'Total');macro=powers(report,'Macro')
    # Macro output load switching belongs to this parent, not its child.
    return total[0]-macro[0]+total[1]+total[2]-macro[2]

def make_header(d,out):
    libs=sorted(p for p in (REPO/'vendor/asap7/lib/NLDM').glob('*RVT_TT_nldm_*') if 'FAKE' not in p.name)
    assert len(libs)==5
    text='set_thread_count 4\n'+''.join(f'read_lef {brace(p)}\n' for p in [REPO/'vendor/asap7/lef/asap7_tech_1x_201209.lef',REPO/'vendor/asap7/lef/asap7sc7p5t_28_R_1x_220121a.lef',Path(d['prepared'])/'pe.lef'])
    text+=''.join(f'read_liberty {brace(p)}\n' for p in [*libs,Path(d['TT_model']['path'])])
    return text

def main(binding,reuse=False,contract_io=False):
    started=time.monotonic();d=json.loads(Path(binding).read_text());directory=Path(binding).parent
    out=directory/'TT_power'
    if not reuse:out.mkdir(exist_ok=False)
    result_path=directory/('estimate_contract.json' if contract_io else 'estimate.json')
    if result_path.exists():raise ValueError('preserve completed estimate')
    for key in ['shell','TT_model']:check(d[key])
    header=make_header(d,out)
    script=header+f'read_verilog {brace(d["shell"]["path"])}\nlink_design npu_systolic_matmul_16x16\n'
    area_helper=REPO/'evaluator/t10_backend/hybrid/cell_area.tcl'
    script+=f'source {brace(area_helper)}\nset areas [t10_cell_area [ord::get_db_block] {brace(d["pe_master"])}]\nputs "T10_HYBRID_LEF_AREA [dict get $areas area_um2] [dict get $areas macro_count]"\n'
    script+=f'set f [open {brace(out/"native_nets.txt")} w]\nforeach net [get_nets -hierarchical *] {{puts $f [string map {{\\\\ ""}} [get_full_name $net]]}}\nclose $f\n'
    script+=f'write_db {brace(out/"unplaced.odb")}\nputs T10_HYBRID_COMPLETE\nexit\n'
    if reuse:
        if (out/'prepare.tcl').read_text()!=script:raise ValueError('prepared context differs')
        prepare_report=(out/'prepare.log').read_text()
        assert 'T10_HYBRID_COMPLETE' in prepare_report and '[ERROR' not in prepare_report
    else:
        (out/'prepare.tcl').write_text(script);prepare_report=native(out/'prepare.tcl',out/'prepare.log')
    area=re.search(r'^T10_HYBRID_LEF_AREA (\S+) (\d+)$',prepare_report,re.M)
    assert area and int(area[2])==d['pe_count']
    if not reuse:
        with (out/'mapping.log').open('x') as stream:
            subprocess.run([sys.executable,str(HERE/'t10_hybrid_activity.py'),binding],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=900)
    # R/C per micrometre are the repository's ASAP7 signal model. Length is
    # intentionally an uncalibrated sensitivity, NOT a physical prediction.
    wl='''library (pilot_wire) {
      delay_model : table_lookup; time_unit : "1ps"; voltage_unit : "1v";
      current_unit : "1mA"; pulling_resistance_unit : "1kohm";
      capacitive_load_unit (1,fF); nom_process : 1; nom_voltage : 0.7; nom_temperature : 25;
      input_threshold_pct_rise : 50; input_threshold_pct_fall : 50;
      output_threshold_pct_rise : 50; output_threshold_pct_fall : 50;
      slew_lower_threshold_pct_rise : 10; slew_upper_threshold_pct_rise : 90;
      slew_lower_threshold_pct_fall : 10; slew_upper_threshold_pct_fall : 90;
    '''
    lengths=[0]
    for length in lengths:
        wl+=f'wire_load (L{length}) {{ resistance : 0.0265684; capacitance : 0.165790; area : 0; slope : {length}; fanout_length (1,{length}); fanout_length (2,{2*length}); }}\n'
    wl+='}\n'
    if reuse:
        if (out/'wire.lib').read_text()!=wl:raise ValueError('wire library differs')
    else:(out/'wire.lib').write_text(wl)
    script=header+f'read_liberty {brace(out/"wire.lib")}\nread_db {brace(out/"unplaced.odb")}\n'
    if contract_io:
        script+='set_cmd_units -time ps -capacitance fF\nsource '+brace(REPO/'evaluator/t10_backend/v1/power_gate.sdc')+'\n'
    else:
        script+='set_cmd_units -time ps -capacitance fF\ncreate_clock -name clk_clock -period 1000 [get_ports clk]\nset_input_delay 200 -clock clk_clock [all_inputs -no_clocks]\nset_output_delay 200 -clock clk_clock [all_outputs]\nset_false_path -from [get_ports rst_n]\nset_input_transition 20 [all_inputs]\nset_load 1 [all_outputs]\n'
    sweep=out/('contract_sweep_v1' if contract_io else 'fresh_sweep_v1');sweep.mkdir(exist_ok=False)
    script+=f'set ::env(T10_ACTIVITY_NETS) {brace(directory/"activity_nets.tsv")}\nsource {brace(REPO/"evaluator/t10_backend/v1/import_saif_activity.tcl")}\n'
    reports=[]
    for length in lengths:
        point=script+f'set_wire_load_model -name L{length} -library pilot_wire\n'
        point+=f'puts "T10_HYBRID_WIRE_LENGTH {length}"\nreport_power -digits 12\n'
        point+='foreach kind {max min} {set p [find_timing_paths -path_delay $kind -sort_by_slack -group_path_count 1]; puts "T10_HYBRID_TIMING $kind [get_property [lindex $p 0] slack]"}\n'
        point+='puts T10_HYBRID_COMPLETE\nexit\n'
        file=sweep/f'L{length}.tcl';file.write_text(point)
        reports.append((length,native(file,file.with_suffix('.log')),file.with_suffix('.log')))
    check(d['old_power']);previous=json.loads(Path(d['old_power']['path']).read_text())
    pe_power=0.0;old_reports=[]
    if 'components' in previous:
        for row in previous['components']:
            record=dict(path=row['report_path'],sha256=row['report_sha256']);check(record)
            pe_power+=accounted(Path(record['path']).read_text());old_reports.append(record)
    else:
        check(previous['power_report']);pe_power=accounted(Path(previous['power_report']['path']).read_text())
        old_reports.append(previous['power_report'])
    duration=json.loads((directory/'activity_mapping.json').read_text())['duration_seconds']
    assert duration==previous['vcd_window_seconds']
    mapping=json.loads((directory/'activity_mapping.json').read_text())
    sensitivities=[];switching=[]
    for length,section,log in reports:
        imported=re.search(r'T10_ACTIVITY_IMPORT nets=(\d+) pins=(\d+) physical_nets_without_activity=(\d+)',section)
        sequential=re.search(r'T10_SEQUENTIAL_ACTIVITY annotated=(\d+) total=(\d+)',section)
        assert imported and int(imported[1])==mapping['native_nets'] and sequential
        assert int(sequential[2])>0 and int(sequential[1])/int(sequential[2])>=.95
        shell=accounted(section);switching.append(powers(section,'Total')[1])
        timing={k:float(v) for k,v in re.findall(r'^T10_HYBRID_TIMING (max|min) (\S+)$',section,re.M)}
        sensitivities.append(dict(assumed_wire_um_per_sink=int(length),shell_power_w=shell,
          whole_power_w=shell+d['pe_count']*pe_power,
          energy_per_matrix_block_nj=(shell+d['pe_count']*pe_power)*duration/200*1e9,
          integrated_estimated_slack_ps=timing,timing_corner='TT',native_report=artifact(log)))
    assert len(sensitivities)==len(lengths)
    assert all(b>=a-1e-15 for a,b in zip(switching,switching[1:]))
    result=dict(label=d['label'],source_sha256=d['source_sha256'],measurement_scope='whole_design',
      status='experimental_prephysical_estimate_not_formal_ppa',formal_ranking_eligible=False,official_scores_changed=False,
      pe_count=d['pe_count'],average_pe_power_w=pe_power,old_pe_report_bindings=old_reports,
      peripheral_lef_cell_area_um2=float(area[1]),area_helper=artifact(area_helper),
      peripheral_activity_import={'nets':int(imported[1]),'pins':int(imported[2]),
        'sequential_pins_annotated':int(sequential[1]),'sequential_pins_total':int(sequential[2])},
      matrix_blocks=200,duration_seconds=duration,sensitivities=sensitivities,
      assumptions=dict(output_load_ff=0 if contract_io else 1,input_transition_ps=0 if contract_io else 20,
        ideal_top_clock=True,wire_length_calibrated=False,io_contract=artifact(REPO/'evaluator/t10_backend/v1/power_gate.sdc') if contract_io else None),
      limitations=d['limitations']+['full clock distribution energy and delay-induced glitches not measured',
        'PE internal power is reused at its original characterization loads; changed external loads add switching only'],
      elapsed_seconds=time.monotonic()-started,script=artifact(__file__),
      native_context_policy='one fresh process per wire model; no cached parasitic estimates reused',
      input_bindings={'activity_table':artifact(directory/'activity_nets.tsv'),'database':artifact(out/'unplaced.odb')})
    result_path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main(sys.argv[1],reuse='--reuse-prepared' in sys.argv[2:],contract_io='--contract-io' in sys.argv[2:])
