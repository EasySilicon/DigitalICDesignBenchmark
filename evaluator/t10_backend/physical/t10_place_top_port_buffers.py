"""Anchor the complete DUT's existing I/O buffers to actual physical pins.

Preserve the entire netlist, all registers, macros and clocks. A cell-only
branch audit misses the final cell-to-port wire; this producer addresses
that boundary geometry rather than reporting it as an internal timing pass.
"""
import argparse
import hashlib
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from t10_localize_gather_combinational import snapshot
from t10_repair_top_clock_channels import NewCellPlacer, distance, xy
from t10_repair_top_data_controls import reserve_local_row


def port_point(port):
    boxes = [box for pin in port.getBPins() for box in pin.getBoxes()]
    if not boxes: raise RuntimeError(f'Physical pin missing: {port.getName()}')
    return (round(statistics.median((b.xMin()+b.xMax())//2 for b in boxes)),
            round(statistics.median((b.yMin()+b.yMax())//2 for b in boxes)))


def main():
    import odb
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input_odb'); p.add_argument('output_odb'); p.add_argument('report_json')
    args = p.parse_args(); started = time.monotonic()
    db = odb.dbDatabase.create(); odb.read_db(db, args.input_odb)
    block = db.getChip().getBlock(); dbu = block.getDbUnitsPerMicron()
    insts = list(block.getInsts()); macros = [i for i in insts if i.getMaster().isBlock()]
    if len(macros) != 16: raise RuntimeError('Require sixteen tile macros in the full DUT')
    plans = defaultdict(list); skipped = Counter()
    port_h = hashlib.sha256()
    for port in sorted(block.getBTerms(),key=lambda t:t.getName()):
        point = port_point(port)
        port_h.update(repr((port.getName(),str(port.getIoType()),point,port.getNet().getName())).encode())
        if port.getName() in ('clk','rst_n') or str(port.getNet().getSigType()) != 'SIGNAL': continue
        kind = str(port.getIoType())
        role = 'OUTPUT' if kind == 'OUTPUT' else 'INPUT'
        pins = [t for t in port.getNet().getITerms() if str(t.getIoType()) == role]
        matched = [t for t in pins if re.fullmatch(r'(input|output)\d+',t.getInst().getName())
                   and t.getInst().getMaster().getName().startswith('BUFx')]
        if not matched: skipped[kind]+=1; continue
        for pin in matched:
            plans[pin.getInst().getName()].append((port.getName(),kind,point,pin.getMTerm().getName()))
    movable = set(plans); before = snapshot(insts,movable)
    placer = NewCellPlacer(block,[i for i in insts if not i.getMaster().isBlock() and i.getName() not in movable])
    before_lengths,after_lengths,moves,reserve_rows = [],[],[],[]
    for index,(name,ports) in enumerate(sorted(plans.items())):
        inst = block.findInst(name)
        before_lengths.extend(distance(xy(inst.findITerm(pin)),point)/dbu for _,_,point,pin in ports)
        target = (round(statistics.median(point[0] for _,_,point,_ in ports)),
                  round(statistics.median(point[1] for _,_,point,_ in ports)))
        old = inst.getLocation(); displacement = placer.place(inst,target)
        if displacement > 100*dbu:
            reserve_rows.append(reserve_local_row(block,placer,inst,target,macros,odb))
            displacement = placer.place(inst,target)
        if displacement > 100*dbu: raise RuntimeError(f'Cannot anchor port buffer within 100 um: {name}')
        lengths = [distance(xy(inst.findITerm(pin)),point)/dbu for _,_,point,pin in ports]
        after_lengths.extend(lengths)
        moves.append({'inst':name,'ports':[port for port,_,_,_ in ports],
                      'old_xy':old,'new_xy':inst.getLocation(),
                      'maximum_cell_to_port_manhattan_um':max(lengths),
                      'legal_target_displacement_um':displacement/dbu})
        if index % 2000 == 0: print(f'T10_PORT_ANCHOR buffers={index}/{len(plans)}',flush=True)
    if snapshot(insts,movable) != before: raise RuntimeError('Netlist/register/macro/clock properties changed')
    if max(after_lengths) > 150: raise RuntimeError('Distant physical port branch remains')
    odb.write_db(db,args.output_odb)
    report = {'diagnostic_only':True,'status':'pending_input_branch_repair_native_placement_and_routed_STA',
              'input_odb':args.input_odb,'tile_macros':16,'pe_count_by_hierarchy':256,
              'instance_count':len(insts),'moved_existing_port_buffers':len(plans),
              'port_buffer_pins_by_direction':dict(Counter(kind for ports in plans.values() for _,kind,_,_ in ports)),
              'skipped_ports_without_dedicated_positive_buffer':dict(skipped),
              'port_geometry_sha256':port_h.hexdigest(),
              'immutable_netlist_register_macro_clock_sha256':before,
              'netlist_register_macro_clock_unchanged':True,
              'maximum_cell_to_port_before_um':max(before_lengths),
              'maximum_cell_to_port_after_um':max(after_lengths),
              'added_local_reserve_rows':reserve_rows,'elapsed_seconds':time.monotonic()-started,
              'moves':moves}
    Path(args.report_json).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='moves'}),flush=True)


if __name__ == '__main__': main()
