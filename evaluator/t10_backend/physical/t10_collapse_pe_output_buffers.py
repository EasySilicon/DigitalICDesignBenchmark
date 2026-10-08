"""Remove verified redundant BUF stages from fixed PE output cones.

The location-guided experiments leave their old long-wire buffer chains
intact.  Once a complete cone is placed next to its output pin, the middle
BUF stages can be bypassed if each output net has exactly one sink.  INV
stages and the final port driver are preserved.
"""

import argparse
import json

import odb


parser = argparse.ArgumentParser()
parser.add_argument("input_odb")
parser.add_argument("output_odb")
parser.add_argument("report_json")
parser.add_argument("selection_json", nargs="+")
args = parser.parse_args()

db = odb.dbDatabase.create()
odb.read_db(db, args.input_odb)
block = db.getChip().getBlock()
selection = []
claimed = set()
for path in args.selection_json:
    bits = json.load(open(path, encoding="utf-8"))["bits"]
    for bit, entry in bits.items():
        chain = entry["cells_from_ff_to_port"]
        for name in chain:
            if name in claimed:
                raise RuntimeError(f"shared cone cell {name}")
            claimed.add(name)
        selection.append((path, bit, chain))

removed = []
for path, bit, chain in selection:
    for name in chain[1:-1]:
        inst = block.findInst(name)
        if inst is None:
            raise RuntimeError(f"missing selected cell {name}")
        if not inst.getMaster().getName().startswith("BUF"):
            continue
        inputs = [term for term in inst.getITerms()
                  if str(term.getIoType()) == "INPUT"]
        outputs = [term for term in inst.getITerms()
                   if str(term.getIoType()) == "OUTPUT"]
        if len(inputs) != 1 or len(outputs) != 1:
            raise RuntimeError(f"unexpected BUF topology at {name}")
        input_net = inputs[0].getNet()
        output_net = outputs[0].getNet()
        if input_net is None or output_net is None:
            raise RuntimeError(f"disconnected BUF {name}")
        sinks = [term for term in output_net.getITerms()
                 if str(term.getIoType()) == "INPUT"]
        if len(sinks) != 1 or list(output_net.getBTerms()):
            raise RuntimeError(f"cannot collapse branched/port BUF {name}")
        sink = sinks[0]
        if sink.getInst().getName() not in chain:
            raise RuntimeError(f"output of {name} escapes selected cone")
        sink.disconnect()
        sink.connect(input_net)
        odb.dbInst_destroy(inst)
        if list(output_net.getITerms()) or list(output_net.getBTerms()):
            raise RuntimeError(f"unexpected remaining terminals on {output_net.getName()}")
        odb.dbNet_destroy(output_net)
        removed.append({"selection": path, "bit": bit, "cell": name})

odb.write_db(db, args.output_odb)
with open(args.report_json, "w", encoding="utf-8") as handle:
    json.dump({"cones": len(selection), "removed_buffers": removed}, handle, indent=2)
    handle.write("\n")
print(f"collapsed {len(removed)} redundant BUF stages in {len(selection)} cones")
