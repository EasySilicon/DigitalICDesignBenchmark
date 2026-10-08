"""Export tested fixed flop locations from an OpenDB diagnostic placement.

Run with OpenROAD's Python interpreter. The resulting Tcl is an ORFS
POST_GLOBAL_PLACE_TCL hook, followed by removal of stale placement buffers.
"""

import argparse
import re

import odb


parser = argparse.ArgumentParser()
parser.add_argument("input_odb")
parser.add_argument("output_tcl")
args = parser.parse_args()

db = odb.dbDatabase.create()
odb.read_db(db, args.input_odb)
block = db.getChip().getBlock()
dbu = block.getDbUnitsPerMicron()
hop_pattern = re.compile(
    r"result_row\\\[([0-3])\\\]\.result_cell\\\[([01])\\\]\."
    r"(data_pipe|slot_pipe|valid_pipe)\\\[([12])\\\]"
)
guard_pattern = re.compile(r"reset_guard\\\[([0-6])\\\]")
targets = []
for inst in block.getInsts():
    name = inst.getName()
    hop = hop_pattern.search(name)
    guard = guard_pattern.search(name)
    if hop:
        _, col, _, stage = hop.groups()
        if (int(col), int(stage)) not in {(0, 1), (0, 2), (1, 1)}:
            continue
    elif not (guard and inst.getMaster().getName().startswith("DFF")):
        continue
    if str(inst.getPlacementStatus()) != "FIRM":
        raise RuntimeError(f"expected FIRM placement: {name}")
    x, y = inst.getLocation()
    targets.append((name, x / dbu, y / dbu, str(inst.getOrient())))

if len(targets) != 535:
    raise RuntimeError(f"expected 528 hop and 7 guard flops, got {len(targets)}")

with open(args.output_tcl, "w", encoding="utf-8") as out:
    out.write("# Generated from diagnosed 1 GHz rowguard placement.\n")
    out.write("# Fix 528 result-hop and 7 reset-guard flops before resizing.\n")
    for name, x, y, orient in sorted(targets):
        out.write(
            f"place_inst -name {{{name}}} -location {{{x:.3f} {y:.3f}}} "
            f"-orientation {orient} -status FIRM\n"
        )
    out.write("remove_buffers\n")
print(f"wrote {len(targets)} fixed placements to {args.output_tcl}")
