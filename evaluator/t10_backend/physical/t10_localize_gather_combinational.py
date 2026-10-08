"""Reduce full-top gather wirelength while fixing every register and clock.

Coordinate descent minimizes real driver/load Manhattan edge lengths for
gather combinational cells. Fixed register, macro, clock, and repeater
positions are anchors. All original logical connections are preserved.
Native placement and routed timing must independently qualify the output.
"""
import argparse
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from t10_repair_top_clock_channels import Channels, NewCellPlacer, distance, xy


def snapshot(insts, movable):
    h = hashlib.sha256()
    for inst in sorted(insts, key=lambda i:i.getName()):
        h.update(repr((inst.getName(), inst.getMaster().getName())).encode())
        if inst.getName() not in movable:
            h.update(repr((inst.getLocation(), str(inst.getOrient()), str(inst.getPlacementStatus()))).encode())
        for pin in sorted(inst.getITerms(), key=lambda t:t.getMTerm().getName()):
            net = pin.getNet()
            h.update(repr((pin.getMTerm().getName(), net.getName() if net else None)).encode())
    return h.hexdigest()


def center(inst):
    box = inst.getBBox()
    return (box.xMin()+box.xMax())//2, (box.yMin()+box.yMax())//2


def main():
    import odb
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_odb')
    parser.add_argument('output_odb')
    parser.add_argument('report_json')
    parser.add_argument('--passes', type=int, default=8)
    args = parser.parse_args()
    started = time.monotonic()
    db = odb.dbDatabase.create(); odb.read_db(db, args.input_odb)
    block = db.getChip().getBlock(); dbu = block.getDbUnitsPerMicron()
    insts = list(block.getInsts())
    macros = [i for i in insts if i.getMaster().isBlock()]
    if len(macros) != 16:
        raise RuntimeError('Require the full DUT with sixteen tile macros')
    moving = [i for i in insts if i.getName().startswith('gather_slot')
              and '/' in i.getName() and not i.getMaster().getName().startswith(('DFF', 'SDFF', 'LATCH'))
              and '/t10_' not in i.getName()
              and not any(t.getNet() and str(t.getNet().getSigType()) == 'CLOCK' for t in i.getITerms())]
    moving.sort(key=lambda i:i.getName())
    movable = {i.getName() for i in moving}
    if not 20000 <= len(moving) <= 160000:
        raise RuntimeError(f'Unexpected gather combinational cell count {len(moving)}')
    before = snapshot(insts, movable)
    channels = Channels(block, macros)
    positions = {i.getName(): center(i) for i in insts}
    neighbors = defaultdict(list)
    edges = []
    for net in block.getNets():
        if str(net.getSigType()) != 'SIGNAL': continue
        roots = [t for t in net.getITerms() if str(t.getIoType()) == 'OUTPUT']
        loads = [t for t in net.getITerms() if str(t.getIoType()) == 'INPUT']
        if len(roots) != 1 or len(loads) > 128: continue
        if any(t.getMTerm().getName() in ('RESETN', 'SETN', 'RN', 'SN', 'rst_n') for t in loads): continue
        root = roots[0]; a = root.getInst().getName()
        for pin in loads:
            b = pin.getInst().getName()
            if a == b or (a not in movable and b not in movable): continue
            # Macro pin locations, rather than macro centers, anchor the
            # gather input. Each macro port has its own immutable node.
            aa, bb = a, b
            if root.getInst().getMaster().isBlock():
                aa = (a, root.getMTerm().getName()); positions[aa] = xy(root)
            if pin.getInst().getMaster().isBlock():
                bb = (b, pin.getMTerm().getName()); positions[bb] = xy(pin)
            edges.append((aa, bb))
            if a in movable: neighbors[a].append(bb)
            if b in movable: neighbors[b].append(aa)
    original_positions = dict(positions)
    def cost(): return sum(distance(positions[a], positions[b]) for a,b in edges)
    initial_cost = cost()
    progress = []
    for iteration in range(args.passes):
        changed = 0
        for inst in moving if iteration % 2 == 0 else reversed(moving):
            name = inst.getName(); adjacent = neighbors[name]
            if not adjacent: continue
            points = [positions[n] for n in adjacent]
            median = (round(statistics.median(p[0] for p in points)),
                      round(statistics.median(p[1] for p in points)))
            candidates = [positions[name]]
            if not any(x0 < median[0] < x1 and y0 < median[1] < y1
                       for x0,y0,x1,y1 in channels.boxes.values()):
                candidates.append(median)
            candidates.extend((x, median[1]) for x in channels.xs)
            candidates.extend((median[0], y) for y in channels.ys)
            target = min(candidates, key=lambda p:(sum(distance(p,q) for q in points),
                                                   distance(p, positions[name]), p))
            if target != positions[name]:
                positions[name] = target; changed += 1
        current_cost = cost()
        progress.append({'pass':iteration+1, 'changed_cells':changed,
                         'driver_load_manhattan_sum_um':current_cost/dbu})
        print('T10_GATHER_LOCALIZE '+json.dumps(progress[-1]), flush=True)
        if not changed: break
    placer = NewCellPlacer(block, [i for i in insts if not i.getMaster().isBlock()
                                   and i.getName() not in movable])
    displacements, legal_displacements = [], []
    for index, inst in enumerate(moving):
        old = center(inst)
        legal_displacements.append(placer.place(inst, positions[inst.getName()])/dbu)
        displacements.append(distance(old, center(inst))/dbu)
        positions[inst.getName()] = center(inst)
        if index % 20000 == 0:
            print(f'T10_GATHER_LOCALIZE placed={index}/{len(moving)}', flush=True)
    if before != snapshot(insts, movable):
        raise RuntimeError('Netlist, register, macro or clock geometry changed')
    final_cost = cost()
    before_lengths = [distance(original_positions[a],original_positions[b])/dbu for a,b in edges]
    after_lengths = [distance(positions[a],positions[b])/dbu for a,b in edges]
    if final_cost >= initial_cost:
        raise RuntimeError('Legalized placement did not improve gather edge wirelength')
    odb.write_db(db, args.output_odb)
    report = {'diagnostic_only':True, 'status':'pending_native_placement_and_routed_STA',
              'input_odb':args.input_odb, 'tile_macros':16, 'pe_count_by_hierarchy':256,
              'instance_count':len(insts), 'moved_combinational_cells':len(moving),
              'immutable_netlist_register_macro_clock_sha256':before,
              'netlist_register_macro_clock_unchanged':True,
              'driver_load_edges':len(edges), 'edge_wirelength_before_um':initial_cost/dbu,
              'edge_wirelength_after_um':final_cost/dbu,
              'long_edges_before':{str(t):sum(v>t for v in before_lengths) for t in (300,500,1000,2000)},
              'long_edges_after':{str(t):sum(v>t for v in after_lengths) for t in (300,500,1000,2000)},
              'maximum_cell_movement_um':max(displacements),
              'maximum_legal_target_displacement_um':max(legal_displacements),
              'passes':progress, 'elapsed_seconds':time.monotonic()-started}
    Path(args.report_json).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='passes'}), flush=True)


if __name__ == '__main__': main()
