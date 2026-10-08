"""Move a PE bottom-edge output register and its buffer cone near each port.

This is a placement experiment. Run with OpenROAD's Python interpreter on
the PE 3_place ODB, then legalize and check timing in OpenROAD Tcl.
"""

import argparse
import json
import re

import odb


parser = argparse.ArgumentParser()
parser.add_argument("input_odb")
parser.add_argument("output_odb")
parser.add_argument("report_json")
parser.add_argument("--prefix", default="b_out")
parser.add_argument("--register-prefix", default="b_out")
parser.add_argument("--count", type=int, default=64)
parser.add_argument("--start-bit", type=int, default=0)
parser.add_argument("--single-register-name")
parser.add_argument("--allow-shared-ff-trial", action="store_true")
parser.add_argument("--row-low-um", type=float, default=19.0)
parser.add_argument("--row-high-um", type=float, default=40.0)
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
        fixed_rects.append((rect.xMin(), rect.yMin(),
                            rect.xMax(), rect.yMax()))
candidate_rows = [
    row for row in rows
    if args.row_low_um * dbu <= row.getOrigin()[1]
    < args.row_high_um * dbu
]
if len(candidate_rows) < args.count:
    raise RuntimeError(f"need {args.count} output corridor rows, got {len(candidate_rows)}")

# Yosys names plain and resettable positive-edge flops as _DFF_P_ and
# _DFF_PN0_, respectively.  Both are valid dedicated boundary registers.
ff_pattern = re.compile(
    re.escape(args.register_prefix) + r"\\\[(\d+)\\\]\$_DFF_(?:P|PN0)_"
)
report = {"bits": {}, "moved_cell_count": 0, "dbu_per_micron": dbu}
claimed = set()

for offset, bit in enumerate(range(args.start_bit, args.start_bit + args.count)):
    port = block.findBTerm(f"{args.prefix}[{bit}]")
    net = block.findNet(f"{args.prefix}[{bit}]")
    if port is None or net is None:
        raise RuntimeError(f"missing {args.prefix}[{bit}] port or net")
    port_boxes = [box for bpin in port.getBPins() for box in bpin.getBoxes()]
    if len(port_boxes) != 1:
        raise RuntimeError(f"unexpected {args.prefix}[{bit}] physical pin count")
    pin_x = (port_boxes[0].xMin() + port_boxes[0].xMax()) // 2

    # The output cone is a single-input buffer/inverter chain rooted at the
    # port-driving flip-flop.  Stop rather than moving a logic cone blindly.
    chain_from_port = []
    while True:
        drivers = [term for term in net.getITerms()
                   if str(term.getIoType()) == "OUTPUT"]
        if len(drivers) != 1:
            raise RuntimeError(f"{args.prefix}[{bit}] net {net.getName()} has "
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

    row = candidate_rows[offset]
    origin_x, row_y = row.getOrigin()
    pitch = row.getSpacing()
    chain = list(reversed(chain_from_port))
    # CTS timing repair may upsize the intermediate output buffers.  Leave
    # enough whitespace for the largest observed BUFx3 -> BUFx6f replacement.
    gap = 20 * pitch
    total_width = sum(inst.getMaster().getWidth() for inst in chain)
    total_width += gap * (len(chain) - 1)
    nominal_x = origin_x + round((pin_x - total_width - origin_x) / pitch) * pitch
    offsets = [0]
    for site in range(1, 75):
        offsets.extend((-site * pitch, site * pitch))
    first_x = None
    for offset in offsets:
        x_test = nominal_x + offset
        trial_x = x_test
        clear = True
        for inst in chain:
            width = inst.getMaster().getWidth()
            height = inst.getMaster().getHeight()
            if any(trial_x < fx1 and trial_x + width > fx0
                   and row_y < fy1 and row_y + height > fy0
                   for fx0, fy0, fx1, fy1 in fixed_rects):
                clear = False
                break
            trial_x += width + gap
        if clear:
            first_x = x_test
            break
    if first_x is None:
        raise RuntimeError(f"no tap-free corridor for {args.prefix}[{bit}]")
    x = first_x
    for inst in chain:
        inst.setOrient(str(row.getOrient()))
        inst.setLocation(x, row_y)
        inst.setPlacementStatus("FIRM")
        x += inst.getMaster().getWidth() + gap
        report["moved_cell_count"] += 1
    report["bits"][str(bit)] = {
        "port_x_um": pin_x / dbu,
        "row_y_um": row_y / dbu,
        "cells_from_ff_to_port": [inst.getName() for inst in chain],
        "cone_width_um": total_width / dbu,
        "offset_from_port_um": (first_x - nominal_x) / dbu,
    }

odb.write_db(db, args.output_odb)
with open(args.report_json, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
    handle.write("\n")
print(f"placed {report['moved_cell_count']} cells in {args.count} output cones")
