"""Buffer long clock branches of the complete T10 top along legal channels.

OpenROAD -python producer. Preserve every original instance and every data
connection. Shared prefixes form a repeater tree. Placement and routed STA
must independently qualify the resulting checkpoint; this is not a pass.
"""
import argparse
import bisect
import hashlib
import heapq
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from t10_sparse_channel_legalize import nearest_gap


def xy(pin):
    box = pin.getBBox()
    return ((box.xMin() + box.xMax()) // 2,
            (box.yMin() + box.yMax()) // 2)


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def intersects(a, b, box):
    x0, y0, x1, y1 = box
    if a[0] == b[0]:
        return x0 < a[0] < x1 and max(a[1], b[1]) > y0 and min(a[1], b[1]) < y1
    if a[1] == b[1]:
        return y0 < a[1] < y1 and max(a[0], b[0]) > x0 and min(a[0], b[0]) < x1
    raise ValueError("Channel route must be orthogonal")


class Channels:
    def __init__(self, block, macros):
        die = block.getDieArea()
        self.dbu = block.getDbUnitsPerMicron()
        self.boxes = {m.getName(): (m.getBBox().xMin(), m.getBBox().yMin(),
                                  m.getBBox().xMax(), m.getBBox().yMax()) for m in macros}
        xbands = sorted({(b[0], b[2]) for b in self.boxes.values()})
        ybands = sorted({(b[1], b[3]) for b in self.boxes.values()})
        if len(xbands) != 4 or len(ybands) != 4:
            raise RuntimeError("Expected a physical 4 by 4 grid of tile macros")
        self.xs = [(die.xMin() + xbands[0][0]) // 2]
        self.xs += [(a[1] + b[0]) // 2 for a, b in zip(xbands, xbands[1:])]
        self.xs += [(xbands[-1][1] + die.xMax()) // 2]
        self.ys = [(die.yMin() + ybands[0][0]) // 2]
        self.ys += [(a[1] + b[0]) // 2 for a, b in zip(ybands, ybands[1:])]
        self.ys += [(ybands[-1][1] + die.yMax()) // 2]
        self.nodes = [(x, y) for x in self.xs for y in self.ys]
        self.adj = defaultdict(list)
        for x in self.xs:
            for ya, yb in zip(self.ys, self.ys[1:]):
                self.edge((x, ya), (x, yb))
        for y in self.ys:
            for xa, xb in zip(self.xs, self.xs[1:]):
                self.edge((xa, y), (xb, y))

    def clear(self, a, b, own_macro=None):
        for name, box in self.boxes.items():
            if not intersects(a, b, box):
                continue
            if name != own_macro:
                return False
            # Permit the macro pin's local access stub, never a shortcut
            # through the macro interior where repeaters cannot be placed.
            axis = 1 if a[0] == b[0] else 0
            overlap = min(max(a[axis], b[axis]), box[axis+2]) - max(min(a[axis], b[axis]), box[axis])
            if overlap > 25 * self.dbu:
                return False
        return True

    def edge(self, a, b):
        if not self.clear(a, b):
            raise RuntimeError("Channel centerline intersects a macro")
        self.adj[a].append(b)
        self.adj[b].append(a)

    def portals(self, point, own_macro=None):
        paths = []
        for x in self.xs:
            projection = (x, point[1])
            if distance(point, projection) <= 100 * self.dbu and self.clear(point, projection, own_macro):
                for y in self.ys:
                    node = (x, y)
                    if self.clear(projection, node):
                        paths.append([point, projection, node])
        for y in self.ys:
            projection = (point[0], y)
            if distance(point, projection) <= 100 * self.dbu and self.clear(point, projection, own_macro):
                for x in self.xs:
                    node = (x, y)
                    if self.clear(projection, node):
                        paths.append([point, projection, node])
        if not paths:
            raise RuntimeError(f"No legal channel portal for {point}")
        return paths

    def tree(self, source):
        costs, paths, heap = {}, {}, []
        for path in self.portals(source):
            node = path[-1]
            cost = sum(distance(a, b) for a, b in zip(path, path[1:]))
            if cost < costs.get(node, math.inf):
                costs[node], paths[node] = cost, path
                heapq.heappush(heap, (cost, node))
        while heap:
            cost, node = heapq.heappop(heap)
            if cost != costs[node]:
                continue
            for other in self.adj[node]:
                candidate = cost + distance(node, other)
                if candidate < costs.get(other, math.inf):
                    costs[other] = candidate
                    paths[other] = paths[node] + [other]
                    heapq.heappush(heap, (candidate, other))
        return costs, paths

    def route(self, source_tree, sink, own_macro=None):
        costs, paths = source_tree
        source = next(iter(paths.values()))[0]
        candidates = []
        # Points on the same channel can connect directly. Routing them
        # through a distant grid intersection creates a needless round trip.
        for corner in ((source[0], sink[1]), (sink[0], source[1])):
            if self.clear(source, corner, own_macro) and self.clear(corner, sink, own_macro):
                candidates.append([source, corner, sink])
        source_portals = self.portals(source)
        sink_portals = self.portals(sink, own_macro)
        for head in source_portals:
            for tail in sink_portals:
                a, b = head[1], tail[1]
                if (a[0] == b[0] or a[1] == b[1]) and self.clear(a,b):
                    candidates.append([source, a, b, sink])
        for tail in sink_portals:
            node = tail[-1]
            candidates.append(paths[node] + list(reversed(tail[:-1])))
        scored = []
        for candidate in candidates:
            points = []
            for point in candidate:
                if not points or point != points[-1]:
                    points.append(point)
            scored.append((sum(distance(a,b) for a,b in zip(points,points[1:])),len(points),points))
        return min(scored)[2]


class NewCellPlacer:
    def __init__(self, block, cells, padding=1):
        self.padding = padding
        self.rows = defaultdict(list)
        self.occupied = defaultdict(list)
        for row in block.getRows():
            self.rows[row.getOrigin()[1]].append(row)
        self.ys = sorted(self.rows)
        for inst in cells:
            box = inst.getBBox()
            found = None
            for row in self.rows[box.yMin()]:
                origin = row.getOrigin()[0]
                pitch = row.getSpacing()
                row_end = origin + row.getSiteCount() * pitch
                if origin <= box.xMin() and box.xMax() <= row_end:
                    start = (box.xMin() - origin) // pitch - padding
                    end = math.ceil((box.xMax() - origin) / pitch) + padding
                    found = row
                    self.occupied[row.getName()].append((max(0, start), min(row.getSiteCount(), end)))
                    break
            if found is None:
                raise RuntimeError(f"Original cell off row: {inst.getName()}")
        for name, intervals in self.occupied.items():
            merged = []
            for start, end in sorted(intervals):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            self.occupied[name] = merged

    def place(self, inst, target):
        width = inst.getMaster().getWidth()
        # The requested position is the buffer center, not its lower left.
        x, y = target[0] - width // 2, target[1] - inst.getMaster().getHeight() // 2
        insert = bisect.bisect_left(self.ys, y)
        left, right = insert - 1, insert
        best = None
        while left >= 0 or right < len(self.ys):
            ld = abs(self.ys[left] - y) if left >= 0 else math.inf
            rd = abs(self.ys[right] - y) if right < len(self.ys) else math.inf
            if best is not None and min(ld, rd) > best[0]:
                break
            if ld <= rd:
                row_y = self.ys[left]
                left -= 1
            else:
                row_y = self.ys[right]
                right += 1
            for row in self.rows[row_y]:
                ox = row.getOrigin()[0]
                pitch = row.getSpacing()
                if width % pitch:
                    raise RuntimeError("Clock buffer width off site pitch")
                span = width // pitch + 2 * self.padding
                start = nearest_gap(self.occupied[row.getName()], row.getSiteCount(), span,
                                    round((x - ox) / pitch) - self.padding)
                if start is None:
                    continue
                cell_x = ox + (start + self.padding) * pitch
                candidate = (abs(cell_x - x) + abs(row_y - y), cell_x, row_y,
                             row.getName(), start, span, row)
                if best is None or candidate[:4] < best[:4]:
                    best = candidate
        if best is None:
            raise RuntimeError("No legal room for new clock buffer")
        delta, cell_x, row_y, name, start, span, row = best
        bisect.insort(self.occupied[name], (start, start + span))
        inst.setOrient(str(row.getOrient()))
        inst.setLocation(cell_x, row_y)
        inst.setPlacementStatus("PLACED")
        return delta


def add_clock_reserve_rows(block, macros, odb):
    """Restore a bounded subset of legal rows removed by the sparse producer.

    About 610 extra Y coordinates cost about 25% more native placement-grid
    memory. Restoring every row would multiply that footprint by sixteen.
    Reuse nearby original row fragments and reject any macro intersection.
    """
    original_rows = list(block.getRows())
    by_y = defaultdict(list)
    for row in original_rows:
        by_y[row.getOrigin()[1]].append(row)
    ys = sorted(by_y)
    height = original_rows[0].getSite().getHeight()
    origin_y = ys[0]
    # Existing sparse rows are 16 site heights apart. Offset by eight and
    # sample every 64 heights (17.28 um for this ASAP7 site). These reserve
    # rows provide actual whitespace without moving any original cells.
    selected = set(range(origin_y + 8 * height, ys[-1], 64 * height))
    for center in Channels(block, macros).ys:
        index = round((center-origin_y) / (16*height))
        selected.add(origin_y + (index*16 + 8)*height)
    macro_boxes = [m.getBBox() for m in macros]
    created = 0
    for y in sorted(selected):
        if y in by_y or not ys[0] <= y <= ys[-1]:
            continue
        closest = min((max(0,bisect.bisect_left(ys,y)-1), min(len(ys)-1,bisect.bisect_left(ys,y))),
                      key=lambda index: abs(ys[index]-y))
        for template in by_y[ys[closest]]:
            x = template.getOrigin()[0]
            end = x + template.getSiteCount()*template.getSpacing()
            if any(x < box.xMax() and end > box.xMin() and y < box.yMax() and y+height > box.yMin()
                   for box in macro_boxes):
                continue
            row = odb.dbRow_create(block, f"t10_clk_reserve_row_{created:05d}", template.getSite(),
                                   x, y, str(template.getOrient()), "HORIZONTAL",
                                   template.getSiteCount(), template.getSpacing())
            if row is None:
                raise RuntimeError("Could not restore legal clock reserve row")
            created += 1
    return {"additional_row_fragments": created, "original_y_count": len(ys),
            "new_y_count": len({r.getOrigin()[1] for r in block.getRows()}),
            "reserve_pitch_um": 64*height/block.getDbUnitsPerMicron()}


def old_fingerprint(insts, ignore_clock=False):
    h = hashlib.sha256()
    for inst in sorted(insts, key=lambda i: i.getName()):
        h.update(repr((inst.getName(), inst.getMaster().getName(), inst.getLocation(),
                       str(inst.getOrient()), str(inst.getPlacementStatus()))).encode())
        for pin in sorted(inst.getITerms(), key=lambda p: p.getMTerm().getName()):
            net = pin.getNet()
            if ignore_clock and net and str(net.getSigType()) == "CLOCK":
                continue
            h.update(repr((pin.getMTerm().getName(), net.getName() if net else None)).encode())
    return h.hexdigest()


def main():
    import odb
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_odb")
    p.add_argument("output_odb")
    p.add_argument("report_json")
    p.add_argument("--spacing-um", type=float, default=200)
    p.add_argument("--threshold-um", type=float, default=300)
    p.add_argument("--buffer", default="BUFx24_ASAP7_75t_SL")
    args = p.parse_args()
    if args.spacing_um <= 0 or args.threshold_um < args.spacing_um:
        p.error("Require positive spacing and threshold at least spacing")
    started = time.monotonic()
    db = odb.dbDatabase.create()
    odb.read_db(db, args.input_odb)
    block = db.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()
    originals = list(block.getInsts())
    macros = [i for i in originals if i.getMaster().isBlock()]
    if len(macros) != 16:
        raise RuntimeError("Full DUT must contain sixteen 4x4 tile macros")
    master = next((lib.findMaster(args.buffer) for lib in db.getLibs()
                   if lib.findMaster(args.buffer)), None)
    if master is None or args.buffer not in {"BUFx24_ASAP7_75t_SL", "BUFx24_ASAP7_75t_R"}:
        raise RuntimeError("Require an explicitly approved noninverting buffer")
    before = old_fingerprint(originals, ignore_clock=True)
    channels = Channels(block, macros)
    row_reserve = add_clock_reserve_rows(block, macros, odb)
    placer = NewCellPlacer(block, [i for i in originals if not i.getMaster().isBlock()])
    spacing = round(args.spacing_um * dbu)
    threshold = args.threshold_um * dbu
    created, repaired, max_move, mutations = [], 0, 0, []
    original_nets = [n for n in block.getNets() if str(n.getSigType()) == "CLOCK"]
    clock_loads = {(pin.getInst().getName(), pin.getMTerm().getName())
                   for net in original_nets for pin in net.getITerms()
                   if str(pin.getIoType()) == "INPUT"}
    original_drivers = {net.getName(): [pin.getInst().getName() for pin in net.getITerms()
                                      if str(pin.getIoType()) == "OUTPUT"] for net in original_nets}
    for net_idx, net in enumerate(sorted(original_nets, key=lambda n: n.getName())):
        drivers = [t for t in net.getITerms() if str(t.getIoType()) == "OUTPUT"]
        if len(drivers) != 1:
            continue
        driver = drivers[0]
        loads = [t for t in net.getITerms() if str(t.getIoType()) == "INPUT"]
        source = xy(driver)
        long_loads = [t for t in loads if distance(source, xy(t)) > threshold]
        if not long_loads:
            continue
        tree = channels.tree(source)
        prefixes = {}
        for sink in sorted(long_loads, key=lambda t: (t.getInst().getName(), t.getMTerm().getName())):
            sink_point = xy(sink)
            own = sink.getInst().getName() if sink.getInst().getMaster().isBlock() else None
            points = channels.route(tree, sink_point, own)
            # Corners and grid edges have deterministic breakpoints, so loads
            # sharing a physical prefix reuse the same inserted buffers.
            targets = []
            for a, b in zip(points, points[1:]):
                length = distance(a, b)
                steps = math.ceil(length / spacing)
                for step in range(1, steps + 1):
                    if b == sink_point and step == steps:
                        continue
                    # Fixed distances from a shared origin are essential:
                    # equal subdivision by each load's total length gives
                    # different first repeaters and destroys prefix sharing.
                    progress = min(step * spacing, length)
                    point = (a[0] + (1 if b[0] > a[0] else -1 if b[0] < a[0] else 0) * progress,
                             a[1] + (1 if b[1] > a[1] else -1 if b[1] < a[1] else 0) * progress)
                    if not targets or targets[-1] != point:
                        targets.append(point)
            previous_net = net
            prefix = ()
            chain = []
            for target in targets:
                prefix += (target,)
                existing = prefixes.get(prefix)
                if existing:
                    inst, previous_net = existing
                else:
                    name = f"t10_clk_channel_repair_{len(created):05d}"
                    if block.findInst(name) or block.findNet(name + "_net"):
                        raise RuntimeError("Clock repair prefix already exists")
                    inst = odb.dbInst_create(block, master, name)
                    a_pin, y_pin = inst.findITerm("A"), inst.findITerm("Y")
                    if a_pin is None or y_pin is None:
                        raise RuntimeError("Expected buffer A/Y pins")
                    a_pin.connect(previous_net)
                    output = odb.dbNet_create(block, name + "_net")
                    output.setSigType("CLOCK")
                    if net.getNonDefaultRule():
                        output.setNonDefaultRule(net.getNonDefaultRule())
                    y_pin.connect(output)
                    for pin in inst.getITerms():
                        kind = str(pin.getSigType())
                        if kind in ("POWER", "GROUND"):
                            supply = block.findNet("VDD" if kind == "POWER" else "VSS")
                            if supply:
                                pin.connect(supply)
                    movement = placer.place(inst, target)
                    if movement > 75 * dbu:
                        raise RuntimeError(f"New clock buffer displaced beyond 75 um: {name} "
                                           f"target={target} actual={inst.getLocation()} move_um={movement/dbu} "
                                           f"net={net.getName()} sink={sink.getInst().getName()} points={points}")
                    max_move = max(max_move, movement)
                    previous_net = output
                    prefixes[prefix] = inst, output
                    created.append(inst)
                chain.append(inst.getName())
            if not chain:
                raise RuntimeError("Long branch did not produce a repeater")
            sink.connect(previous_net)
            mutations.append({"sink": sink.getInst().getName(), "pin": sink.getMTerm().getName(),
                              "original_net": net.getName(), "driver": driver.getInst().getName(),
                              "buffer_chain": chain, "path_um": sum(distance(a,b) for a,b in zip(points,points[1:])) / dbu})
            repaired += 1
        if net_idx % 100 == 0:
            print(f"T10_CLOCK_CHANNEL_REPAIR nets={net_idx}/{len(original_nets)} "
                  f"branches={repaired} buffers={len(created)} elapsed={time.monotonic()-started:.1f}", flush=True)
    after = old_fingerprint(originals, ignore_clock=True)
    if before != after:
        raise RuntimeError("Repair changed old geometry, masters, or non-clock connectivity")
    # Each recorded path must consist solely of inserted positive buffers and
    # must reconnect to its exact original driver through the original net.
    for mutation in mutations:
        expected_net = block.findNet(mutation["original_net"])
        for name in mutation["buffer_chain"]:
            inst = block.findInst(name)
            if inst.getMaster().getName() != args.buffer or inst.findITerm("A").getNet() != expected_net:
                raise RuntimeError("Buffer-chain connectivity/polarity check failed")
            expected_net = inst.findITerm("Y").getNet()
        if block.findInst(mutation["sink"]).findITerm(mutation["pin"]).getNet() != expected_net:
            raise RuntimeError("Sink connection missing")
    lengths, fanouts = [], []
    now_loads = set()
    for net in block.getNets():
        if str(net.getSigType()) != "CLOCK":
            continue
        drivers = [pin for pin in net.getITerms() if str(pin.getIoType()) == "OUTPUT"]
        inputs = [pin for pin in net.getITerms() if str(pin.getIoType()) == "INPUT"]
        for pin in inputs:
            if not pin.getInst().getName().startswith("t10_clk_channel_repair_"):
                now_loads.add((pin.getInst().getName(), pin.getMTerm().getName()))
        if len(drivers) > 1:
            raise RuntimeError("Multiple clock drivers")
        if len(drivers) == 1:
            lengths.extend(distance(xy(drivers[0]), xy(pin)) / dbu for pin in inputs)
            fanouts.append(len(inputs))
    if now_loads != clock_loads or any(original_drivers[n.getName()] !=
        [t.getInst().getName() for t in n.getITerms() if str(t.getIoType()) == "OUTPUT"] for n in original_nets):
        raise RuntimeError("Original clock load/driver set changed")
    if max(lengths) > max(args.threshold_um, args.spacing_um + 150) + 5:
        raise RuntimeError(f"Long clock branch remains after physical placement: {max(lengths)} um")
    output = Path(args.output_odb)
    output.parent.mkdir(parents=True, exist_ok=True)
    odb.write_db(db, str(output))
    report = {"status": "produced_pending_native_placement_and_routed_STA", "diagnostic_only": True,
              "input_odb": args.input_odb, "old_geometry_and_data_connectivity_sha256": before,
              "old_instances_unchanged": True, "original_clock_loads_preserved": True,
              "tile_macro_count": 16, "pe_count_by_hierarchy": 256,
              "original_instances": len(originals), "inserted_noninverting_buffers": len(created),
              "instance_count": len(block.getInsts()), "repaired_branches": repaired,
              "buffer_master": args.buffer, "target_spacing_um": args.spacing_um,
              "repair_threshold_um": args.threshold_um, "max_new_cell_displacement_um": max_move/dbu,
              "max_clock_branch_manhattan_um": max(lengths), "max_clock_net_fanout": max(fanouts),
              "long_branches_by_threshold_um": {str(t): sum(v>t for v in lengths) for t in (300,500,1000,2000)},
              "channel_centers_x_um": [x/dbu for x in channels.xs],
              "channel_centers_y_um": [y/dbu for y in channels.ys],
              "clock_reserve_rows": row_reserve,
              "elapsed_seconds": time.monotonic()-started, "mutations": mutations}
    Path(args.report_json).write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k != "mutations"}), flush=True)


if __name__ == "__main__":
    main()
