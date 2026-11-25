"""Charge primary-input receiver capacitance exactly once, including clock."""
import gzip,json,math,re
from pathlib import Path
from t10_hybrid_ppa import REPO,artifact
from t10_hybrid_power import make_header,native
from t10_candidate_power import brace

def input_caps(binding):
    d=json.loads(Path(binding).read_text());folder=Path(binding).parent;out=folder/'input_capacitance_r3';out.mkdir(exist_ok=False)
    text=make_header(d,out)+f'read_db {brace(folder/"TT_power/unplaced.odb")}\nset_cmd_units -time ps -capacitance fF\nsource {brace(REPO/"evaluator/t10_backend/v1/power_gate.sdc")}\n'
    text+=f'set f [open {brace(out/"nets.tsv")} w]\n'
    text+='''set seen [dict create]
set data_inputs [all_inputs -no_clocks]
set top [sta::top_instance]
foreach port [all_inputs] {
    set port_pin [$top find_pin [get_property $port name]]
    set term [$port_pin term]
    if {$term eq "NULL"} {error "top input lacks an internal terminal"}
    set nets [list [$term net]]
    foreach net $nets {
        if {$net eq "NULL"} {continue}
        set name [string map {\\\\ ""} [get_full_name $net]]
        if {[dict exists $seen $name]} {continue}
        dict set seen $name 1
        set cap 0.0
        set sinks 0
        foreach pin [get_pins -of_objects $net] {
            if {[get_property $pin direction] ne "input"} {continue}
            set libport [$pin liberty_port]
            if {$libport eq "NULL"} {continue}
            set cap [expr {$cap+[$libport capacitance [sta::cmd_scene] max]}]
            incr sinks
        }
        set physical [[ord::get_db_block] findNet $name]
        if {$physical eq "NULL"} {error "missing input physical net"}
        foreach bterm [$physical getBTerms] {
            if {[$bterm getIoType] eq "OUTPUT"} {incr sinks}
        }
        set clock [expr {[lsearch -exact $data_inputs $port]<0}]
        puts $f "$name\t$sinks\t$cap\t$clock"
    }
}
close $f
puts T10_HYBRID_COMPLETE
exit
'''
    p=out/'export.tcl';p.write_text(text);native(p,out/'export.log')
    activities={}
    for line in (folder/'activity_nets.tsv').read_text().splitlines():
        match=re.fullmatch(r'\{(.*)\} (\S+) (\S+)',line);assert match
        activities[match[1]]=float(match[2])
    voltage=[]
    for lib in (REPO/'vendor/asap7/lib/NLDM').glob('*RVT_TT_nldm_*'):
        if 'FAKE' in lib.name:continue
        source=gzip.open(lib,'rt').read() if lib.suffix=='.gz' else lib.read_text()
        voltage.append(float(re.search(r'\bnom_voltage\s*:\s*(\S+)\s*;',source)[1]))
    assert len(voltage)==5 and len(set(voltage))==1
    inputs=[]
    for line in (out/'nets.tsv').read_text().splitlines():
        name,sinks,cap,clock=line.split('\t');sinks=int(sinks);cap=float(cap);clock=bool(int(clock))
        assert name in activities and math.isfinite(cap) and cap>=0
        inputs.append((name,sinks,cap,activities[name],clock))
    if not inputs or not any(x[4] for x in inputs) or not any(x[2]>0 for x in inputs):
        raise ValueError('incomplete or empty primary-input capacitance coverage')
    rc_source=REPO/'vendor/asap7/setRC.tcl'
    rc_text=rc_source.read_text()
    wire_c={kind:float(re.search(r'set_wire_rc -'+kind+r' -resistance\s+\S+\s+-capacitance\s+(\S+)',rc_text)[1])*1e-15 for kind in ['signal','clock']}
    old=json.loads((folder/'estimate_contract.json').read_text());rows=[]
    for sensitivity in old['sensitivities']:
        length=sensitivity['assumed_wire_um_per_sink']
        components={kind:sum(.5*(cap+wire_c['clock' if clock else 'signal']*length*sinks)*voltage[0]**2*density for _,sinks,cap,density,clock in inputs if ('clock' if clock else 'signal')==kind) for kind in ['clock','signal']}
        watts=sum(components.values())
        rows.append(dict(assumed_wire_um_per_sink=length,primary_input_capacitor_charging_w=watts,
          clock_input_charging_w=components['clock'],data_input_charging_w=components['signal'],
          whole_estimated_power_including_input_loads_w=sensitivity['whole_power_w']+watts,
          whole_estimated_energy_per_matrix_block_nj=(sensitivity['whole_power_w']+watts)*old['duration_seconds']/200*1e9))
    result=dict(label=d['label'],status='primary_input_load_ledger',voltage_v=voltage[0],input_nets=len(inputs),
      includes='ideal charging of input-driven receiver and estimated wire capacitance; external driver internal power excluded',
      limitations='same uncalibrated fanout wire model; no physical top clock-tree internal power',
      rows=rows,rc_source=artifact(rc_source),native_table=artifact(out/'nets.tsv'),script=artifact(__file__))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result
