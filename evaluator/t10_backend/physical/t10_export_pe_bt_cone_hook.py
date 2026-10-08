"""Export the 111-cell bt_out cone placement as an ORFS placement hook.

Run with OpenROAD's Python interpreter.  The JSON comes from the matching
output-cone placement experiment and fixes the selected cell set.
"""

import argparse
import json

import odb

parser = argparse.ArgumentParser()
parser.add_argument("input_odb")
parser.add_argument("cone_report_json")
parser.add_argument("output_tcl")
args = parser.parse_args()

with open(args.cone_report_json, encoding="utf-8") as handle:
    report = json.load(handle)
names = [name for bit in range(27)
         for name in report["bits"][str(bit)]["cells_from_ff_to_port"]]
if len(names) != 111 or len(set(names)) != 111:
    raise RuntimeError("expected exactly 111 distinct PE output-cone cells")

db = odb.dbDatabase.create()
odb.read_db(db, args.input_odb)
block = db.getChip().getBlock()
dbu = block.getDbUnitsPerMicron()
with open(args.output_tcl, "w", encoding="utf-8") as out:
    out.write("# Keep each bt_out register, inverter, and output buffer near its pin.\n")
    for name in names:
        inst = block.findInst(name)
        if inst is None or str(inst.getPlacementStatus()) != "FIRM":
            raise RuntimeError(f"missing or nonfixed cone cell: {name}")
        x, y = inst.getLocation()
        out.write(
            f"place_inst -name {{{name}}} "
            f"-location {{{x / dbu:.3f} {y / dbu:.3f}}} "
            f"-orientation {inst.getOrient()} -status FIRM\n"
        )
print(f"wrote {len(names)} fixed PE output-cone cells to {args.output_tcl}")
