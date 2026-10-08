"""Repair selected full-DUT control branches with positive RVT repeaters.

Preserve every original instance, its placement, and all unmodified pins.
For each modified input, independently walk the inserted buffer chain back
to its exact original net. This is a diagnostic producer, not routed signoff.
"""
import argparse
import bisect
import hashlib
import json
import math
import re
import time
from pathlib import Path

from t10_repair_top_clock_channels import Channels, NewCellPlacer, distance, xy


class SignalChannels(Channels):
    """Permit a signal macro output's own short pin-access stub.

    Signal sources include macro outputs; the clock-channel helper assumed
    sources outside macros. Its existing 25 um stub bound still applies.
    """
    def portals(self, point, own_macro=None):
        if own_macro is None:
            containing = [name for name, box in self.boxes.items()
                          if box[0] <= point[0] <= box[2]
                          and box[1] <= point[1] <= box[3]]
            if len(containing) > 1:
                raise RuntimeError('Signal endpoint belongs to multiple macros')
            if containing:
                own_macro = containing[0]
        return super().portals(point, own_macro)


def pin_key(pin):
    return pin.getInst().getName(), pin.getMTerm().getName()


def snapshot(insts, omitted):
    h = hashlib.sha256()
    for inst in sorted(insts, key=lambda i: i.getName()):
        h.update(repr((inst.getName(), inst.getMaster().getName(), inst.getLocation(),
                       str(inst.getOrient()), str(inst.getPlacementStatus()))).encode())
        for pin in sorted(inst.getITerms(), key=lambda t: t.getMTerm().getName()):
            if pin_key(pin) in omitted:
                continue
            net = pin.getNet()
            h.update(repr((pin.getMTerm().getName(), net.getName() if net else None)).encode())
    return h.hexdigest()


def signal_inputs(inst):
    return [t for t in inst.getITerms() if str(t.getIoType()) == 'INPUT'
            and t.getNet() and str(t.getNet().getSigType()) == 'SIGNAL'
            and t.getMTerm().getName() not in ('RESETN', 'SETN', 'RN', 'SN', 'rst_n')]


def selected_nets(block, control_scope, output_data, minimum_controller_fanout=0):
    """Control repeaters and their real upstream combinational cones."""
    if control_scope == 'signals':
        # Full-DUT repair includes low-fanout data/control long wires as
        # well as high-fanout controllers. Never touch clocks or reset.
        nets=[]
        for net in block.getNets():
            if str(net.getSigType()) != 'SIGNAL': continue
            if net.getName() in ('clk','rst_n'): continue
            loads=[t for t in net.getITerms() if str(t.getIoType())=='INPUT']
            if any(t.getMTerm().getName() in ('clk','CLK','CK','SN','RN','RESETN','SETN','rst_n') for t in loads): continue
            nets.append(net)
        return sorted(nets,key=lambda n:n.getName()),0
    controls = [i for i in block.getInsts()
                if re.search(r't10_(finalpop|finalpush|writeptr)_s[0-3]c\d+r', i.getName())]
    if control_scope != 'raw' and len(controls) != 2304:
        raise RuntimeError(f'Expected 2304 existing control buffers, got {len(controls)}')
    if control_scope in ('all', 'raw'):
        names = {i.getName() for i in controls}
        controls.extend(i for i in block.getInsts() if i.getName() not in names
                        and re.search(r'(?:^|/)t10_(rowsel|gatherready|prefetch|outready|gvalid|rowread)',
                                      i.getName()))
    selected = {}
    pending = []
    for inst in controls:
        y = inst.findITerm('Y')
        if not y or not inst.getMaster().getName().startswith('BUFx'):
            raise RuntimeError('Unexpected original control repeater')
        selected[y.getNet().getName()] = y.getNet()
        pending.extend(t.getNet() for t in signal_inputs(inst))
    if control_scope in ('all', 'raw'):
        # The anonymous top-level cells implement the shared token, format,
        # queue and credit controller. Include their real cones as well as
        # the named distribution trees; otherwise the next scalar source
        # simply retains another unbuffered multi-millimeter branch.
        for inst in block.getInsts():
            if not re.fullmatch(r'_\d+_', inst.getName()):
                continue
            if inst.getMaster().isBlock() or inst.getMaster().getName().startswith(('DFF', 'SDFF', 'LATCH')):
                continue
            for pin in inst.getITerms():
                if str(pin.getIoType()) == 'OUTPUT' and pin.getNet() and str(pin.getNet().getSigType()) == 'SIGNAL':
                    if sum(str(t.getIoType()) == 'INPUT' for t in pin.getNet().getITerms()) < minimum_controller_fanout:
                        continue
                    pending.append(pin.getNet())
        if control_scope == 'raw' and minimum_controller_fanout:
            for net in block.getNets():
                if str(net.getSigType()) != 'SIGNAL': continue
                loads = [t for t in net.getITerms() if str(t.getIoType()) == 'INPUT']
                if len(loads) >= minimum_controller_fanout and not any(
                    t.getMTerm().getName() in ('RESETN','SETN','RN','SN','rst_n') for t in loads):
                    pending.append(net)
    # Include externally visible handshake/metadata cones. They must not
    # conceal a repaired internal path behind a still-unbuffered output
    # branch. Datapath ports are deliberately excluded from this small ECO.
    for port in block.getBTerms():
        patterns = r'^(out_valid|out_row|out_block_id|in_ready)(\[|$)'
        if output_data:
            patterns = r'^(out_valid|out_row|out_block_id|out_data|in_ready)(\[|$)'
        if re.match(patterns, port.getName()):
            if port.getNet():
                pending.append(port.getNet())
        if control_scope in ('all', 'raw') and str(port.getIoType()) == 'INPUT' \
                and port.getName() not in ('clk', 'rst_n') and port.getNet():
            for pin in port.getNet().getITerms():
                inst = pin.getInst()
                if str(pin.getIoType()) == 'INPUT' and re.fullmatch(r'input\d+',inst.getName()) \
                        and inst.getMaster().getName().startswith('BUFx'):
                    output = inst.findITerm('Y')
                    if output and output.getNet(): pending.append(output.getNet())
    visited = set()
    while pending:
        net = pending.pop()
        if net.getName() in visited:
            continue
        visited.add(net.getName())
        if str(net.getSigType()) != 'SIGNAL':
            raise RuntimeError('Control cone reached a nonsignal net')
        drivers = [t for t in net.getITerms() if str(t.getIoType()) == 'OUTPUT']
        if len(drivers) != 1:
            continue
        selected[net.getName()] = net
        inst = drivers[0].getInst()
        master = inst.getMaster().getName()
        if inst.getMaster().isBlock() or master.startswith(('DFF', 'SDFF', 'LATCH')):
            continue
        pending.extend(t.getNet() for t in signal_inputs(inst))
    return sorted(selected.values(), key=lambda n: n.getName()), len(controls)


def targets_on_path(points, sink, spacing):
    targets = []
    for a, b in zip(points, points[1:]):
        length = distance(a, b)
        for step in range(1, math.ceil(length / spacing) + 1):
            if b == sink and step == math.ceil(length / spacing):
                continue
            progress = min(step * spacing, length)
            point = tuple(a[k] + (1 if b[k] > a[k] else -1 if b[k] < a[k] else 0) * progress
                          for k in range(2))
            if not targets or point != targets[-1]:
                targets.append(point)
    return targets


def reserve_local_row(block, placer, inst, target, macros, odb):
    """Add one legal row fragment at a crowded target, bounded to 64 new Ys.

    Reuse a nearby site's geometry and even row-height offsets, preserving
    row orientation. Reject intersections with macros or existing rows.
    This improves local capacity without restoring the dense full-chip grid.
    """
    dbu = block.getDbUnitsPerMicron()
    existing = [r for r in block.getRows() if r.getName().startswith('t10_data_control_reserve_')]
    if len({r.getOrigin()[1] for r in existing}) >= 64:
        raise RuntimeError('Data reserve reached its 64-Y memory bound')
    height = inst.getMaster().getHeight()
    candidates = []
    die = block.getDieArea()
    nearby = sorted(block.getRows(), key=lambda r:abs(r.getOrigin()[1]-target[1]))[:160]
    # Full vertical-channel fragments at adjacent Ys ensure that a wide
    # horizontal row near a macro is never incorrectly copied inside it.
    for template in nearby:
        ox, oy = template.getOrigin()
        end = ox + template.getSiteCount()*template.getSpacing()
        horizontal_distance = max(ox-target[0], target[0]-end, 0)
        if horizontal_distance > 100*dbu: continue
        for offset in (-8,-4,-2,2,4,8):
            y = oy + offset*height
            if y < die.yMin() or y+height > die.yMax(): continue
            if any(ox < m.getBBox().xMax() and end > m.getBBox().xMin()
                   and y < m.getBBox().yMax() and y+height > m.getBBox().yMin() for m in macros): continue
            if any(ox < r.getOrigin()[0] + r.getSiteCount()*r.getSpacing()
                   and end > r.getOrigin()[0] for r in placer.rows.get(y, [])): continue
            candidates.append((horizontal_distance+abs(y-target[1]), y, ox, template))
    if not candidates:
        raise RuntimeError(f'No legal local reserve row at {target}')
    _, y, ox, template = min(candidates, key=lambda v:v[:3])
    number = max((int(r.getName().rsplit('_',1)[1]) for r in existing),default=-1)+1
    name = f't10_data_control_reserve_{number:04d}'
    row = odb.dbRow_create(block, name, template.getSite(), ox, y,
                           str(template.getOrient()), 'HORIZONTAL',
                           template.getSiteCount(), template.getSpacing())
    if row is None: raise RuntimeError('Could not create local reserve row')
    # place() inserted one exact occupancy interval. Remove just that new
    # cell's interval before trying the additional fragment; old occupancy
    # and all original instance positions remain unchanged.
    box = inst.getBBox()
    for old_row in placer.rows[box.yMin()]:
        origin = old_row.getOrigin()[0]; pitch = old_row.getSpacing()
        if origin <= box.xMin() and box.xMax() <= origin+old_row.getSiteCount()*pitch:
            start = (box.xMin()-origin)//pitch-placer.padding
            span = inst.getMaster().getWidth()//pitch+2*placer.padding
            placer.occupied[old_row.getName()].remove((start,start+span))
            break
    else: raise RuntimeError('Cannot release new buffer occupancy')
    if y not in placer.rows: bisect.insort(placer.ys, y)
    placer.rows[y].append(row)
    return name


def main():
    import odb
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_odb')
    parser.add_argument('output_odb')
    parser.add_argument('report_json')
    parser.add_argument('--spacing-um', type=float, default=200)
    parser.add_argument('--threshold-um', type=float, default=300)
    parser.add_argument('--control-scope', choices=('output', 'all', 'raw', 'signals'), default='output')
    parser.add_argument('--output-data', action='store_true')
    parser.add_argument('--minimum-controller-fanout', type=int, default=0)
    parser.add_argument('--root-buffer', action='store_true')
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--max-displacement-um', type=float, default=100)
    args = parser.parse_args()
    if not 0 < args.spacing_um <= args.threshold_um:
        parser.error('Require positive spacing no larger than threshold')
    start = time.monotonic()
    db = odb.dbDatabase.create()
    odb.read_db(db, args.input_odb)
    block = db.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()
    originals = list(block.getInsts())
    macros = [i for i in originals if i.getMaster().isBlock()]
    if len(macros) != 16:
        raise RuntimeError('Expected the complete DUT with sixteen tile macros')
    master_name = 'BUFx24_ASAP7_75t_R'
    master = next((lib.findMaster(master_name) for lib in db.getLibs()
                   if lib.findMaster(master_name)), None)
    if master is None:
        raise RuntimeError('Missing approved positive RVT buffer')
    nets, old_controls = selected_nets(block, args.control_scope, args.output_data,
                                      args.minimum_controller_fanout)
    plans, skipped_reset_nets = [], []
    for net in nets:
        drivers = [t for t in net.getITerms() if str(t.getIoType()) == 'OUTPUT']
        if len(drivers) != 1:
            continue
        loads = [t for t in net.getITerms() if str(t.getIoType()) == 'INPUT']
        if any(t.getMTerm().getName() in ('RESETN', 'SETN', 'RN', 'SN', 'rst_n') for t in loads):
            skipped_reset_nets.append(net.getName())
            continue
        long_loads = [t for t in loads if distance(xy(drivers[0]), xy(t)) > args.threshold_um * dbu]
        root_required = args.root_buffer and len(loads) > 16
        if long_loads or root_required:
            plans.append((net, drivers[0], sorted(loads if root_required else long_loads, key=pin_key), root_required))
    changed = {pin_key(t) for _, _, loads, _ in plans for t in loads}
    if args.plan_only:
        lengths = [distance(xy(driver), xy(sink))/dbu
                   for _, driver, loads, _ in plans for sink in loads]
        report = {'diagnostic_only': True, 'physical_qualification_passed': False,
                  'plan_only': True, 'input_odb': args.input_odb,
                  'tile_macros': len(macros), 'control_scope': args.control_scope,
                  'selected_nets': len(nets), 'planned_nets': len(plans),
                  'planned_sink_branches': len(lengths),
                  'planned_root_buffers': sum(root for _, _, _, root in plans),
                  'maximum_manhattan_um': max(lengths, default=0),
                  'sum_manhattan_um': sum(lengths),
                  'spacing_um': args.spacing_um, 'threshold_um': args.threshold_um,
                  'unshared_manhattan_segment_estimate': sum(
                      max(0, math.ceil(length/args.spacing_um)-1) for length in lengths),
                  'estimate_note': 'Resource estimate only; ignores shared prefixes, legal channel detours and displacement.',
                  'elapsed_seconds': time.monotonic()-start}
        Path(args.report_json).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2), flush=True)
        return
    before = snapshot(originals, changed)
    channels = SignalChannels(block, macros)
    placer = NewCellPlacer(block, [i for i in originals if not i.getMaster().isBlock()])
    mutations, inserted, max_move, reserve_rows = [], [], 0, []
    previous_ids = [int(i.getName().rsplit('_', 1)[1]) for i in originals
                    if re.fullmatch(r't10_data_control_repair_\d+', i.getName())]
    first_id = max(previous_ids, default=-1) + 1
    spacing = round(args.spacing_um * dbu)
    root_buffer_count = 0
    for index, (net, driver, loads, root_required) in enumerate(plans):
        tree = channels.tree(xy(driver))
        prefixes = {}
        root_net, root_chain = net, []
        if root_required:
            name = f't10_data_control_repair_{first_id + len(inserted):05d}'
            if block.findInst(name) or block.findNet(name + '_net'):
                raise RuntimeError('Root repair name collision')
            inst = odb.dbInst_create(block, master, name)
            inst.findITerm('A').connect(net)
            root_net = odb.dbNet_create(block, name + '_net'); root_net.setSigType('SIGNAL')
            inst.findITerm('Y').connect(root_net)
            for pin in inst.getITerms():
                kind = str(pin.getSigType())
                if kind in ('POWER', 'GROUND'):
                    supply = block.findNet('VDD' if kind == 'POWER' else 'VSS')
                    if supply: pin.connect(supply)
            target = xy(driver)
            movement = placer.place(inst, target)
            if movement > args.max_displacement_um * dbu:
                reserve_rows.append(reserve_local_row(block, placer, inst, target, macros, odb))
                movement = placer.place(inst, target)
            if movement > args.max_displacement_um * dbu:
                raise RuntimeError(f'Root buffer exceeds displacement limit: {name}')
            max_move = max(max_move, movement)
            inserted.append(inst); root_chain = [name]; root_buffer_count += 1
        for sink in loads:
            sink_point = xy(sink)
            own = sink.getInst().getName() if sink.getInst().getMaster().isBlock() else None
            path = channels.route(tree, sink_point, own)
            previous, prefix, chain = root_net, (), list(root_chain)
            targets = [] if root_required and distance(xy(driver), sink_point) <= args.threshold_um*dbu \
                        else targets_on_path(path, sink_point, spacing)
            for target in targets:
                prefix += (target,)
                if prefix in prefixes:
                    inst, previous = prefixes[prefix]
                else:
                    name = f't10_data_control_repair_{first_id + len(inserted):05d}'
                    if block.findInst(name) or block.findNet(name + '_net'):
                        raise RuntimeError('Data repair name collision')
                    inst = odb.dbInst_create(block, master, name)
                    inst.findITerm('A').connect(previous)
                    output = odb.dbNet_create(block, name + '_net')
                    output.setSigType('SIGNAL')
                    inst.findITerm('Y').connect(output)
                    for pin in inst.getITerms():
                        kind = str(pin.getSigType())
                        if kind in ('POWER', 'GROUND'):
                            supply = block.findNet('VDD' if kind == 'POWER' else 'VSS')
                            if supply:
                                pin.connect(supply)
                    movement = placer.place(inst, target)
                    if movement > args.max_displacement_um * dbu:
                        reserve_rows.append(reserve_local_row(block, placer, inst, target, macros, odb))
                        movement = placer.place(inst, target)
                    if movement > args.max_displacement_um * dbu:
                        raise RuntimeError(f'New buffer exceeds displacement limit: {name} {movement/dbu}')
                    max_move = max(max_move, movement)
                    previous = output
                    prefixes[prefix] = inst, previous
                    inserted.append(inst)
                chain.append(inst.getName())
            if not chain:
                raise RuntimeError('Long branch produced no repeater')
            sink.connect(previous)
            mutations.append({'sink': pin_key(sink), 'original_net': net.getName(),
                              'driver': pin_key(driver), 'chain': chain,
                              'original_manhattan_um': distance(xy(driver), sink_point)/dbu,
                              'route_um': sum(distance(a,b) for a,b in zip(path,path[1:]))/dbu})
        if index % 100 == 0:
            print(f'T10_DATA_CONTROL_REPAIR nets={index}/{len(plans)} buffers={len(inserted)}', flush=True)
    if snapshot(originals, changed) != before:
        raise RuntimeError('Original geometry, clock or unmodified connection changed')
    # Verify each changed input independently by reverse traversal. This
    # verifies positive polarity, absence of cycles and the original root.
    names = {i.getName() for i in inserted}
    for m in mutations:
        cursor = block.findInst(m['sink'][0]).findITerm(m['sink'][1]).getNet()
        walked = []
        while cursor.getName() != m['original_net']:
            roots = [t for t in cursor.getITerms() if str(t.getIoType()) == 'OUTPUT']
            if len(roots) != 1:
                raise RuntimeError('Inserted chain driver count is not one')
            inst = roots[0].getInst()
            if inst.getName() not in names or inst.getName() in walked or inst.getMaster() != master:
                raise RuntimeError('Inserted chain polarity/root/cycle violation')
            walked.append(inst.getName())
            cursor = inst.findITerm('A').getNet()
        if walked != list(reversed(m['chain'])):
            raise RuntimeError('Independent chain walk differs from recorded mutation')
    lengths = []
    for net in [*[n for n in nets if n.getName() not in skipped_reset_nets],
                *[i.findITerm('Y').getNet() for i in inserted]]:
        roots = [t for t in net.getITerms() if str(t.getIoType()) == 'OUTPUT']
        if len(roots) != 1:
            continue
        lengths.extend(distance(xy(roots[0]), xy(t))/dbu for t in net.getITerms()
                       if str(t.getIoType()) == 'INPUT')
    if max(lengths) > max(args.threshold_um, args.spacing_um + 150) + 5:
        raise RuntimeError(f'Selected control branch still too long: {max(lengths)}')
    odb.write_db(db, args.output_odb)
    report = {'diagnostic_only': True, 'status': 'pending_native_placement_and_routed_STA',
              'input_odb': args.input_odb, 'tile_macros': 16, 'pe_count_by_hierarchy': 256,
              'original_instance_count': len(originals), 'instance_count': len(block.getInsts()),
              'original_control_repeaters': old_controls, 'selected_nets': len(nets),
              'control_scope': args.control_scope, 'includes_output_data_cones': args.output_data,
              'minimum_controller_fanout': args.minimum_controller_fanout,
              'inserted_local_root_buffers': root_buffer_count,
              'includes_scalar_top_controller_cones': args.control_scope in ('all', 'raw'),
              'excluded_reset_or_constant_control_nets': skipped_reset_nets,
              'repaired_nets': len(plans), 'repaired_branches': len(mutations),
              'inserted_positive_rvt_buffers': len(inserted), 'buffer_master': master_name,
              'original_geometry_clock_unmodified_connections_sha256': before,
              'original_geometry_and_clock_unchanged': True,
              'independent_positive_chain_equivalence_passed': True,
              'mapped_functional_qualification_passed': False,
              'max_new_cell_displacement_um': max_move/dbu,
              'new_cell_displacement_limit_um': args.max_displacement_um,
              'added_local_reserve_rows': reserve_rows,
              'max_selected_branch_manhattan_um': max(lengths),
              'elapsed_seconds': time.monotonic()-start, 'mutations': mutations}
    Path(args.report_json).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'mutations'}), flush=True)


if __name__ == '__main__':
    main()
