"""Place a PE output-register bank and its complete buffer cones by pins.

Run with OpenROAD's Python interpreter on a placed PE ODB.  The script
requires a single-driver BUF/INV chain for every bit and refuses to
move shared or combinational logic cones.
"""

import argparse
import json
import re

import odb


parser = argparse.ArgumentParser()
parser.add_argument("input_odb")
parser.add_argument("output_odb")
parser.add_argument("report_json")
parser.add_argument("--prefix", default="a_out")
parser.add_argument("--register-prefix", default="a_out")
parser.add_argument("--count", type=int, default=64)
parser.add_argument("--start-bit", type=int, default=0)
parser.add_argument("--single-register-name")
parser.add_argument("--allow-shared-ff-trial", action="store_true")
parser.add_argument("--scalar-port", action="store_true")
args = parser.parse_args()

db = odb.dbDatabase.create()
odb.read_db(db, args.input_odb)
block = db.getChip().getBlock()
dbu = block.getDbUnitsPerMicron()
rows = sorted(block.getRows(), key=lambda row: row.getOrigin()[1])
fixed_rects = []
for fixed_inst in block.getInsts():
    if str(fixed_inst.getPlacementStatus()) in ("LOCKED", "FIRM"):
        rect = fixed_inst.getBBox()
        fixed_rects.append((rect.xMin(), rect.yMin(), rect.xMax(), rect.yMax()))

# Yosys names plain and resettable positive-edge flops as _DFF_P_ and
# _DFF_PN0_, respectively.  Both are valid dedicated boundary registers.
ff_pattern = re.compile(
    re.escape(args.register_prefix) + r"\\\[(\d+)\\\]\$_DFF_(?:P|PN0)_"
)
report = {"bits": {}, "moved_cell_count": 0, "dbu_per_micron": dbu}
claimed = set()

for bit in range(args.start_bit, args.start_bit + args.count):
    port_name = args.prefix if args.scalar_port else f"{args.prefix}[{bit}]"
    port = block.findBTerm(port_name)
    net = block.findNet(port_name)
    if port is None or net is None:
        raise RuntimeError(f"missing {port_name} port or net")
    boxes = [box for bpin in port.getBPins() for box in bpin.getBoxes()]
    if len(boxes) != 1:
            raise RuntimeError(f"unexpected {port_name} physical pin count")
    pin_x = (boxes[0].xMin() + boxes[0].xMax()) // 2
    pin_y = (boxes[0].yMin() + boxes[0].yMax()) // 2

    chain_from_port = []
    while True:
        drivers = [term for term in net.getITerms()
                   if str(term.getIoType()) == "OUTPUT"]
        if len(drivers) != 1:
            raise RuntimeError(f"{port_name} net {net.getName()} has "
                               f"{len(drivers)} drivers")
        inst = drivers[0].getInst()
        name = inst.getName()
        if name in claimed:
            raise RuntimeError(f"shared output cone cell {name}")
        claimed.add(name)
        chain_from_port.append(inst)
        ff_match = ff_pattern.fullmatch(name)
        single_match = (args.single_register_name is not None
                        and name == args.single_register_name
                        and args.count == 1)
        if ff_match or single_match:
            if ff_match and int(ff_match.group(1)) != bit:
                raise RuntimeError(f"wrong output flop for bit {bit}: {name}")
            output_nets = [term.getNet() for term in inst.getITerms()
                           if str(term.getIoType()) == "OUTPUT"]
            if len(output_nets) != 1:
                raise RuntimeError(f"unexpected output pins on {name}")
            sinks = [term for term in output_nets[0].getITerms()
                     if str(term.getIoType()) == "INPUT"]
            if len(sinks) != 1 and not args.allow_shared_ff_trial:
                raise RuntimeError(f"shared output flop {name} has "
                                   f"{len(sinks)} loads; clone it before moving")
            break
        master = inst.getMaster().getName()
        if not (master.startswith("BUF") or master.startswith("INV")):
            raise RuntimeError(f"non-buffer in {args.prefix}[{bit}] cone: {name}")
        inputs = [term for term in inst.getITerms()
                  if str(term.getIoType()) == "INPUT"]
        if len(inputs) != 1 or inputs[0].getNet() is None:
            raise RuntimeError(f"unexpected input topology in {name}")
        net = inputs[0].getNet()

    chain = list(reversed(chain_from_port))
    # Reserve sites for CTS/post-CTS timing repair to enlarge output buffers.
    candidate_rows = sorted(rows, key=lambda row: abs(row.getOrigin()[1] - pin_y))
    found = None
    for row in candidate_rows[:400]:
        origin_x, row_y = row.getOrigin()
        pitch = row.getSpacing()
        row_height = row.getSite().getHeight()
        blocked_x = [(fx0, fx1) for fx0, fy0, fx1, fy1 in fixed_rects
                     if row_y < fy1 and row_y + row_height > fy0]
        gap = 20 * pitch
        total_width = sum(inst.getMaster().getWidth() for inst in chain)
        total_width += gap * (len(chain) - 1)
        row_right = origin_x + pitch * row.getSiteCount()
        if pin_x < origin_x or pin_x > row_right + 2 * dbu:
            continue
        nominal_x = origin_x + round((min(pin_x, row_right) - total_width
                                      - 10 * dbu - origin_x)
                                    / pitch) * pitch
        for shift in range(0, 101):
            x_test = nominal_x - shift * pitch
            if x_test < origin_x or x_test + total_width > row_right:
                continue
            trial_x = x_test
            clear = True
            for inst in chain:
                width = inst.getMaster().getWidth()
                height = inst.getMaster().getHeight()
                if any(trial_x < fx1 and trial_x + width > fx0
                       for fx0, fx1 in blocked_x):
                    clear = False
                    break
                trial_x += width + gap
            if clear:
                found = (row, x_test, total_width, gap)
                break
        if found:
            break
    if found is None:
        raise RuntimeError(f"no legal corridor for {args.prefix}[{bit}]")

    row, x, total_width, gap = found
    row_y = row.getOrigin()[1]
    cells = []
    for inst in chain:
        inst.setOrient(str(row.getOrient()))
        inst.setLocation(x, row_y)
        inst.setPlacementStatus("FIRM")
        width = inst.getMaster().getWidth()
        height = inst.getMaster().getHeight()
        fixed_rects.append((x, row_y, x + width, row_y + height))
        cells.append(inst.getName())
        x += width + gap
        report["moved_cell_count"] += 1
    report["bits"][str(bit)] = {
        "port_x_um": pin_x / dbu,
        "port_y_um": pin_y / dbu,
        "row_y_um": row_y / dbu,
        "cells_from_ff_to_port": cells,
        "cone_width_um": total_width / dbu,
    }

odb.write_db(db, args.output_odb)
with open(args.report_json, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
    handle.write("\n")
print(f"placed {report['moved_cell_count']} cells in {args.count} output cones")
