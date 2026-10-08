"""Place the complete transport DUT using actual tile read pins as anchors.

Diagnostic placement producer: preserves the mapped netlist and fixed macro
geometry, copies the existing constrained physical I/O locations, places
gather registers and gates together, then legalizes every standard cell.
Native placement and routed STA are separate required checks.
"""
import argparse
import hashlib
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from t10_localize_gather_combinational import snapshot, center
from t10_place_top_port_buffers import port_point
from t10_repair_top_clock_channels import Channels, NewCellPlacer, distance, xy


def median(points):
    return tuple(round(statistics.median(p[k] for p in points)) for k in (0, 1))


def main():
    import odb
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('input_odb', 'geometry_odb', 'output_odb', 'report_json'):
        p.add_argument(arg)
    p.add_argument('--distributed-egress', action='store_true')
    args = p.parse_args()
    if Path(args.output_odb).exists():
        raise RuntimeError('Refuse to overwrite a produced checkpoint')
    started = time.monotonic()
    db = odb.dbDatabase.create(); odb.read_db(db, args.input_odb)
    prior_db = odb.dbDatabase.create(); odb.read_db(prior_db, args.geometry_odb)
    block = db.getChip().getBlock(); prior = prior_db.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()
    insts = list(block.getInsts())
    macros = [i for i in insts if i.getMaster().isBlock()]
    cells = [i for i in insts if not i.getMaster().isBlock()]
    assert len(macros) == 16 and dbu == prior.getDbUnitsPerMicron()
    for inst in macros:
        old = prior.findInst(inst.getName())
        assert old and old.getLocation() == inst.getLocation()
        assert str(old.getOrient()) == str(inst.getOrient())
        assert old.getMaster().getName() == inst.getMaster().getName()
    # Preserve the established interface geometry rather than inventing a
    # favorable unconstrained pin placement for this RTL candidate.
    ports = list(block.getBTerms())
    missing = {t.getName() for t in prior.getBTerms()} - {t.getName() for t in ports}
    added = {t.getName() for t in ports} - {t.getName() for t in prior.getBTerms()}
    assert not added and missing <= {'VDD', 'VSS'}, (missing, added)
    for name in sorted(missing):
        old = prior.findBTerm(name)
        assert str(old.getSigType()) in ('POWER', 'GROUND')
        net = block.findNet(old.getNet().getName())
        if not net: net = odb.dbNet.create(block, old.getNet().getName())
        net.setSigType(str(old.getSigType()))
        port = odb.dbBTerm.create(net, name)
        port.setIoType(str(old.getIoType())); port.setSigType(str(old.getSigType()))
    ports = list(block.getBTerms())
    for port in ports:
        old = prior.findBTerm(port.getName())
        assert str(old.getIoType()) == str(port.getIoType())
        for pin in list(port.getBPins()): odb.dbBPin.destroy(pin)
        for pin in old.getBPins():
            new = odb.dbBPin.create(port)
            new.setPlacementStatus(str(pin.getPlacementStatus()))
            for box in pin.getBoxes():
                layer = db.getTech().findLayer(box.getTechLayer().getName())
                odb.dbBox.create(new, layer, box.xMin(), box.yMin(), box.xMax(), box.yMax())
    def port_hash(b):
        h = hashlib.sha256()
        for port in sorted(b.getBTerms(), key=lambda t: t.getName()):
            h.update(repr((port.getName(), str(port.getIoType()), port_point(port),
                           port.getNet().getName())).encode())
        return h.hexdigest()
    old_io_sha = port_hash(block)
    assert old_io_sha == port_hash(prior)
    immutable = snapshot(insts, {i.getName() for i in cells})
    rows = list(block.getRows()); ys = sorted({r.getOrigin()[1] for r in rows})
    keep = set(ys[::16]) | {ys[-1]}
    for row in rows:
        if row.getOrigin()[1] not in keep: odb.dbRow.destroy(row)
    channels = Channels(block, macros)
    def project(point):
        candidates = [(x, point[1]) for x in channels.xs]
        candidates += [(point[0], y) for y in channels.ys]
        return min(candidates, key=lambda q: (distance(point, q), q))
    macro_map = {}
    for inst in macros:
        match = re.search(r'tile_row\[(\d)\]\.tile_col\[(\d)\]\.tile$', inst.getName().replace('\\', ''))
        assert match, inst.getName()
        macro_map[tuple(map(int, match.groups()))] = inst
    lane_anchors = {}
    for group in range(4):
        for column in range(16):
            tile = macro_map[group, column // 4]
            pins = [tile.findITerm(f'read_data[{r*256+(column%4)*64+b}]')
                    for r in range(4) for b in range(38)]
            assert all(pins)
            lane_anchors[group, column] = project(median([xy(t) for t in pins]))
    if args.distributed_egress:
        # User-authorized block I/O distribution: place data slices in the
        # channel beside their own tile, rather than at a global south edge.
        # M7 signal shapes have legal width/minimum area, 256 nm vertical
        # spacing and stay outside macro obstructions. No clock-layer change.
        layer = db.getTech().findLayer('M7')
        assert layer
        def pin_box(name, point):
            port = block.findBTerm(name); assert port
            for pin in list(port.getBPins()): odb.dbBPin.destroy(pin)
            x = round(point[0]/64)*64; y = round(point[1]/64)*64
            pin = odb.dbBPin.create(port); pin.setPlacementStatus('FIRM')
            odb.dbBox.create(pin, layer, x-16, y-64, x+16, y+64)
            for macro in macros:
                box = macro.getBBox()
                assert not (x-16 < box.xMax() and x+16 > box.xMin()
                            and y-64 < box.yMax() and y+64 > box.yMin())
        for g in range(4):
            for tc in range(4):
                tile = macro_map[g,tc]; box = tile.getBBox()
                cy = (box.yMin()+box.yMax())//2
                for c in range(4):
                    for bit in range(64):
                        pin_box(f'out_data[{g*1024+tc*256+c*64+bit}]',
                                (box.xMax()+(20+c*8)*dbu, cy+(bit-31.5)*256))
                if tc == 0:
                    for bit in range(16):
                        pin_box(f'out_block_id[{g*16+bit}]', (box.xMax()+60*dbu,cy+bit*256))
                    for bit in range(4):
                        pin_box(f'out_row[{g*4+bit}]', (box.xMax()+68*dbu,cy+bit*256))
                    pin_box(f'out_valid[{g}]', (box.xMax()+76*dbu,cy))
    io_sha = port_hash(block)
    positions = {i.getName(): center(i) for i in macros}
    hard, categories = {}, Counter()
    warm_started = 0
    for inst in cells:
        name = inst.getName()
        normalized = name.replace('\\', '')
        gather = re.match(r'gather_slot\[(\d)\]\.gather_group\[(\d)\]\.gather_cell\[(\d+)\]\.gather_lane/', normalized)
        transport = re.match(r'gather_transport_slot\[(\d)\]\.gather_transport_group\[(\d)\]\.gather_transport_cell\[(\d+)\]\.transport_lane/', normalized)
        if gather:
            _, group, col = map(int, gather.groups())
            hard[name] = lane_anchors[group, col]
            categories['gather_cells'] += 1
            if inst.getMaster().getName().startswith(('DFF', 'SDFF')):
                categories['gather_register_cells'] += 1
        elif transport:
            _, group, col = map(int, transport.groups())
            hard[name] = project(median([lane_anchors[2*group, col], lane_anchors[2*group+1, col]]))
            categories['transport_cells'] += 1
        elif args.distributed_egress:
            egress = re.match(r'distributed_output_row\[(\d)\]\.tile_column\[(\d)\]\.egress/', normalized)
            if egress:
                group, tc = map(int,egress.groups())
                column = re.search(r'/local_column\[(\d)\](?:[./])',normalized)
                if column:
                    col = tc*4+int(column.group(1)); hard[name] = lane_anchors[group,col]
                else:
                    hard[name] = project(median([lane_anchors[group,tc*4+c] for c in range(4)]))
                categories['distributed_egress_cells'] += 1
            # Keep every named boundary register at its actual row/column
            # endpoints; generic coordinate descent must not scatter them.
            if inst.getMaster().getName().startswith(('DFF','SDFF')):
                def tile_pin(axis,lane,kind,bit):
                    tile = macro_map[lane//4,0] if axis=='a' else macro_map[0,lane//4]
                    width = 64 if kind=='data' else 28
                    pin = tile.findITerm(f'{axis}_in_{kind}[{(lane%4)*width+bit}]')
                    assert pin; return xy(pin)
                def source_pin(axis,lane,kind,bit):
                    width = 64 if kind=='data' else 16
                    port = block.findBTerm(f'{axis}_{kind}[{lane*width+bit}]')
                    assert port; return port_point(port)
                match = re.match(r'([ab])_ctrl_(payload|valid)\[(\d+)\](?:\[(\d+)\])?',normalized)
                if match:
                    axis,kind,lane,bit = match.groups()
                    hard[name] = project(tile_pin(axis,int(lane),'token',27 if kind=='valid' else 16+int(bit)))
                    categories['boundary_control_registers'] += 1
                else:
                    match = re.match(r'([ab])_(edge|skew)_(data|scale)\[(\d+)\]\[(\d+)\]',normalized)
                    if match:
                        axis,stage,kind,index,bit = match.groups(); index=int(index);bit=int(bit)
                        lane=index if stage=='edge' else index//15
                        step=1 if stage=='edge' else index%15+2
                        assert lane<16 and step<=lane+1
                        a=source_pin(axis,lane,kind,bit)
                        b=tile_pin(axis,lane,'data' if kind=='data' else 'token',bit)
                        hard[name]=project(tuple(round(a[k]+step/(lane+1)*(b[k]-a[k])) for k in (0,1)))
                        categories['boundary_data_scale_registers'] += 1
                    else:
                        match=re.match(r'([ab])_scale_hold\[(\d+)\]\[(\d+)\]',normalized)
                        if match:
                            axis,lane,bit=match.groups();hard[name]=project(tile_pin(axis,int(lane),'token',int(bit)))
                            categories['boundary_scale_hold_registers']+=1
                        else:
                            match=re.match(r'ingress_([ab])_(data|scale)\[(\d+)\]',normalized)
                            if match:
                                axis,kind,index=match.groups(); index=int(index);width=64 if kind=='data' else 16
                                hard[name]=project(source_pin(axis,index//width,kind,index%width))
                                categories['ingress_registers']+=1
        old = prior.findInst(name)
        if old and old.getMaster().getName() == inst.getMaster().getName():
            positions[name] = center(old); warm_started += 1
        else:
            positions[name] = (channels.xs[2], channels.ys[2])
    if args.distributed_egress:
        assert categories['distributed_egress_cells'] > 1000
        assert categories['boundary_control_registers'] >= 352
        assert categories['boundary_data_scale_registers'] > 20000
        # The measured v114 worst path crossed the die centre repeatedly
        # through anonymous out_valid/accept gates. Place each slot's real
        # combinational interface cone beside its canonical output. Stop at
        # state elements and egress hierarchy; never change connectivity.
        control_targets = defaultdict(list)
        for group in range(4):
            port = block.findBTerm(f'out_valid[{group}]')
            anchor = project(port_point(port))
            pending = [port.getNet()]
            for pin in port.getNet().getITerms():
                inst = pin.getInst()
                if str(pin.getIoType()) != 'INPUT' or not re.fullmatch(r'_\d+_',inst.getName()):
                    continue
                if inst.getMaster().getName().startswith('AND2'):
                    inputs = [t.getNet() for t in inst.getITerms()
                              if str(t.getIoType())=='INPUT' and t.getNet()]
                    if any(n.getName()=='out_ready' for n in inputs):
                        pending.extend(t.getNet() for t in inst.getITerms()
                                       if str(t.getIoType())=='OUTPUT' and t.getNet())
            visited = set()
            group_control_names = set()
            while pending:
                net = pending.pop()
                if net.getName() in visited: continue
                visited.add(net.getName())
                roots = [t for t in net.getITerms() if str(t.getIoType())=='OUTPUT']
                if len(roots)!=1: continue
                inst=roots[0].getInst(); master=inst.getMaster()
                if master.isBlock() or master.getName().startswith(('DFF','SDFF','LATCH','TIE')):
                    continue
                if not re.fullmatch(r'_\d+_',inst.getName()): continue
                control_targets[inst.getName()].append(anchor)
                group_control_names.add(inst.getName())
                pending.extend(t.getNet() for t in inst.getITerms()
                               if str(t.getIoType())=='INPUT' and t.getNet()
                               and str(t.getNet().getSigType())=='SIGNAL')
            assert group_control_names, ('No output interface cone', group)
        for name, targets in control_targets.items():
            hard[name] = project(median(targets))
        categories['output_interface_control_cells'] = len(control_targets)
        # The local-accept RTL removes the four old top AND gates. Require
        # a real cone for every slot, not an obsolete architecture's count.
        assert categories['output_interface_control_cells'] >= 4
    else:
        assert categories['gather_cells'] > 80000 and categories['transport_cells'] > 10000
    before_positions = dict(positions)
    positions.update(hard)
    adjacent = defaultdict(list); edges = []; read_edges = []
    for net in block.getNets():
        if str(net.getSigType()) != 'SIGNAL': continue
        loads = [t for t in net.getITerms() if str(t.getIoType()) == 'INPUT']
        if any(t.getMTerm().getName() in ('RN','SN','RESETN','SETN','rst_n') for t in loads): continue
        roots = [t for t in net.getITerms() if str(t.getIoType()) == 'OUTPUT']
        sources = [(t.getInst().getName(), t) for t in roots]
        for port in net.getBTerms():
            if str(port.getIoType()) == 'INPUT':
                key = ('port', port.getName()); positions[key] = port_point(port)
                before_positions[key] = positions[key]; sources.append((key, None))
        if len(sources) != 1 or len(loads) > 128: continue
        a, root = sources[0]
        if root and root.getInst().getMaster().isBlock():
            a = ('pin', root.getInst().getName(), root.getMTerm().getName())
            positions[a] = xy(root); before_positions[a] = positions[a]
        sinks = []
        for pin in loads:
            b = pin.getInst().getName()
            if pin.getInst().getMaster().isBlock():
                b = ('pin', b, pin.getMTerm().getName())
                positions[b] = xy(pin); before_positions[b] = positions[b]
            sinks.append(b)
        for port in net.getBTerms():
            if str(port.getIoType()) == 'OUTPUT':
                b = ('port', port.getName()); positions[b] = port_point(port)
                before_positions[b] = positions[b]; sinks.append(b)
        for b in sinks:
            if a == b: continue
            edges.append((a,b))
            adjacent[a].append(b); adjacent[b].append(a)
            if root and root.getInst().getMaster().isBlock() and root.getMTerm().getName().startswith('read_data['):
                read_edges.append((a,b))
    generic = sorted((i for i in cells if i.getName() not in hard), key=lambda i:i.getName())
    for iteration in range(4):
        for inst in generic if iteration % 2 == 0 else reversed(generic):
            name = inst.getName()
            if adjacent[name]: positions[name] = project(median([positions[n] for n in adjacent[name]]))
        print(f'T10_SPATIAL_GENERIC_PASS {iteration+1}', flush=True)
    placer = NewCellPlacer(block, [])
    ordered = sorted(cells, key=lambda i: (0 if i.getName() in hard else 1,
                                          -i.getMaster().getWidth(), i.getName()))
    legal_displacements = []
    for index, inst in enumerate(ordered):
        legal_displacements.append(placer.place(inst, positions[inst.getName()])/dbu)
        positions[inst.getName()] = center(inst)
        if index % 20000 == 0: print(f'T10_SPATIAL_LEGALIZE {index}/{len(ordered)}', flush=True)
    assert snapshot(insts, {i.getName() for i in cells}) == immutable
    assert port_hash(block) == io_sha
    def lengths(pos, selected):
        values = [distance(pos[a], pos[b])/dbu for a,b in selected]
        return {'branches':len(values), 'maximum_um':max(values),
                'sum_um':sum(values),
                'above_um':{str(n):sum(v>n for v in values) for n in (100,300,500,1000,2000)}}
    read_before, read_after = lengths(before_positions, read_edges), lengths(positions, read_edges)
    if not args.distributed_egress:
        assert read_after['maximum_um'] < read_before['maximum_um']
    odb.write_db(db, args.output_odb)
    report = {'diagnostic_only':True, 'physical_qualification_passed':False,
              'status':'pending_native_placement_and_routed_STA',
              'tile_macros':16, 'pe_count_by_hierarchy':256, 'instance_count':len(insts),
              'standard_cell_count':len(cells), 'row_stride':16,
              'warm_started_cells':warm_started, 'hard_anchor_categories':dict(categories),
              'netlist_and_macro_geometry_unchanged':True, 'immutable_sha256':immutable,
              'physical_port_geometry_sha256':io_sha, 'copied_power_ports':sorted(missing),
              'distributed_egress':args.distributed_egress,
              'prior_physical_port_geometry_sha256':old_io_sha,
              'io_policy_note':'Distributed M7 block outputs beside their source tiles; unchanged logical ports and SDC' if args.distributed_egress else 'Prior I/O positions preserved',
              'macro_read_data_before_um':read_before, 'macro_read_data_after_um':read_after,
              'all_sampled_signal_branches_after_um':lengths(positions,edges),
              'maximum_legal_target_displacement_um':max(legal_displacements),
              'elapsed_seconds':time.monotonic()-started}
    Path(args.report_json).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__': main()
