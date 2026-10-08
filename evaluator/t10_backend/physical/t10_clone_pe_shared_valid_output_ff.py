"""Clone a shared PE valid FF for a dedicated physical output cone.

The copy receives the same D, CLK and asynchronous reset nets as the
original.  The original keeps driving internal logic; only the dedicated
output inverter moves to the clone.  Input ODBs must have the same netlist,
with the second ODB carrying a legal trial placement for the output cone.
"""

import argparse
import json

import odb


parser = argparse.ArgumentParser()
parser.add_argument("base_odb")
parser.add_argument("trial_odb")
parser.add_argument("trial_report_json")
parser.add_argument("output_odb")
parser.add_argument("output_report_json")
parser.add_argument("--source-register", default="at_out_valid$_DFF_PN0_")
parser.add_argument("--clone-name", default="at_out_valid_output_clone")
parser.add_argument("--bit", default="27")
args = parser.parse_args()

db = odb.dbDatabase.create()
odb.read_db(db, args.base_odb)
block = db.getChip().getBlock()
trial_db = odb.dbDatabase.create()
odb.read_db(trial_db, args.trial_odb)
trial_block = trial_db.getChip().getBlock()
selected = json.load(open(args.trial_report_json, encoding="utf-8"))["bits"][args.bit]
chain = selected["cells_from_ff_to_port"]
original_name = args.source_register
if chain[0] != original_name:
    raise RuntimeError(f"unexpected source FF {chain[0]}")

original = block.findInst(original_name)
trial_ff = trial_block.findInst(original_name)
if original is None or trial_ff is None:
    raise RuntimeError("missing valid FF")
clone_name = args.clone_name
if block.findInst(clone_name):
    raise RuntimeError("clone already exists")
clone = odb.dbInst_create(block, original.getMaster(), clone_name)
clone.setOrient(str(trial_ff.getOrient()))
clone.setLocation(*trial_ff.getLocation())
clone.setPlacementStatus("FIRM")
new_net = odb.dbNet_create(block, clone_name + "__qn")
if new_net is None:
    raise RuntimeError("cannot create clone output net")

pin_map = {term.getMTerm().getName(): term for term in original.getITerms()}
for term in clone.getITerms():
    pin = term.getMTerm().getName()
    old = pin_map[pin]
    if str(term.getIoType()) == "OUTPUT":
        term.connect(new_net)
    elif old.getNet() is not None:
        term.connect(old.getNet())

boundary_driver = block.findInst(chain[1])
if boundary_driver is None or not boundary_driver.getMaster().getName().startswith(("BUF", "INV")):
    raise RuntimeError("expected output buffer/inverter immediately after clone")
driver_inputs = [term for term in boundary_driver.getITerms()
                   if str(term.getIoType()) == "INPUT"]
if len(driver_inputs) != 1:
    raise RuntimeError("unexpected boundary-driver topology")
old_output_net = driver_inputs[0].getNet()
original_output_nets = {
    term.getNet() for term in original.getITerms()
    if str(term.getIoType()) == "OUTPUT" and term.getNet() is not None
}
if old_output_net not in original_output_nets:
    raise RuntimeError("output branch no longer driven by original FF")
driver_inputs[0].disconnect()
driver_inputs[0].connect(new_net)

for name in chain[1:]:
    inst = block.findInst(name)
    trial_inst = trial_block.findInst(name)
    if inst is None or trial_inst is None:
        raise RuntimeError(f"missing output cone cell {name}")
    inst.setOrient(str(trial_inst.getOrient()))
    inst.setLocation(*trial_inst.getLocation())
    inst.setPlacementStatus("FIRM")

loads = [term.getInst().getName() for term in old_output_net.getITerms()
         if str(term.getIoType()) == "INPUT"]
if len(loads) != 1:
    raise RuntimeError(f"original FF must retain one internal load, got {loads}")
copy_loads = [term.getInst().getName() for term in new_net.getITerms()
              if str(term.getIoType()) == "INPUT"]
if copy_loads != [boundary_driver.getName()]:
    raise RuntimeError(f"clone must drive only output boundary cell, got {copy_loads}")

odb.write_db(db, args.output_odb)
with open(args.output_report_json, "w", encoding="utf-8") as handle:
    json.dump({
        "original_register": original_name,
        "clone_register": clone_name,
        "original_internal_load": loads[0],
        "clone_output_load": copy_loads[0],
        "shared_input_pins": [pin for pin, term in pin_map.items()
                              if str(term.getIoType()) == "INPUT"],
        "output_cone": chain[1:],
    }, handle, indent=2)
    handle.write("\n")
print(f"cloned {original_name} as {clone_name}; isolated output branch")
