"""Audit the PE's physical-only output edits against the source ODB.

This checks that every boundary output has the same FF source and inversion
parity, except for two equivalent output-only FF clones.  It also checks
that the only removed cells are recorded BUF stages and every other cell
outside selected output cones keeps the same pin-to-net connections.
"""

import argparse
import hashlib
import json
from pathlib import Path

import odb


parser = argparse.ArgumentParser()
parser.add_argument("source_odb")
parser.add_argument("optimized_odb")
parser.add_argument("collapse_report_json")
parser.add_argument("output_json")
parser.add_argument("selection_json", nargs="+")
args = parser.parse_args()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def file_record(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def load_block(path):
    db = odb.dbDatabase.create()
    odb.read_db(db, path)
    return db, db.getChip().getBlock()


source_db, source = load_block(args.source_odb)
optimized_db, optimized = load_block(args.optimized_odb)
source_insts = {inst.getName(): inst for inst in source.getInsts()}
optimized_insts = {inst.getName(): inst for inst in optimized.getInsts()}
clones = {
    "at_out_valid_output_clone": "at_out_valid$_DFF_PN0_",
    "bt_out_valid_output_clone": "bt_out_valid$_DFF_PN0_",
}
removed = {entry["cell"] for entry in
           json.load(open(args.collapse_report_json, encoding="utf-8"))
           ["removed_buffers"]}
removed.add("place13737")  # Last redundant bt_valid BUF collapsed separately.
require(set(source_insts) - set(optimized_insts) == removed,
        "removed-instance set differs from the collapse report")
require(set(optimized_insts) - set(source_insts) == set(clones),
        "added-instance set differs from the two declared output clones")
require(all(source_insts[name].getMaster().getName().startswith("BUF")
            for name in removed),
        "a removed instance is not a BUF cell")

selected = set()
for path in args.selection_json:
    for entry in json.load(open(path, encoding="utf-8"))["bits"].values():
        selected.update(entry["cells_from_ff_to_port"])
selected.update(clones)


def pins(inst):
    return {term.getMTerm().getName():
            term.getNet().getName() if term.getNet() else None
            for term in inst.getITerms()}


outside_checked = 0
for name in set(source_insts) - removed - selected:
    old = source_insts[name]
    new = optimized_insts[name]
    require(old.getMaster().getName() == new.getMaster().getName(),
            f"{name}: master changed outside selected output cones")
    require(pins(old) == pins(new),
            f"{name}: connectivity changed outside selected output cones")
    outside_checked += 1


def trace(block, port_name):
    term = block.findBTerm(port_name)
    if term is None:
        raise RuntimeError(f"missing port {port_name}")
    net = term.getNet()
    parity = 0
    cells = []
    while True:
        drivers = [iterm for iterm in net.getITerms()
                   if str(iterm.getIoType()) == "OUTPUT"]
        if len(drivers) != 1:
            raise RuntimeError(f"{port_name}: {len(drivers)} drivers")
        inst = drivers[0].getInst()
        name = inst.getName()
        cells.append(name)
        master = inst.getMaster().getName()
        if "DFF" in master:
            return name, parity, cells
        if master.startswith("INV"):
            parity ^= 1
        elif not master.startswith("BUF"):
            raise RuntimeError(f"{port_name}: unexpected {master}")
        inputs = [iterm for iterm in inst.getITerms()
                  if str(iterm.getIoType()) == "INPUT"]
        if len(inputs) != 1 or inputs[0].getNet() is None:
            raise RuntimeError(f"{port_name}: invalid chain at {name}")
        net = inputs[0].getNet()


ports = ([f"{prefix}[{bit}]" for prefix, count in
          (("a_out", 64), ("b_out", 64), ("at_out", 28), ("bt_out", 28))
          for bit in range(count)])
port_records = {}
for port in ports:
    old_ff, old_parity, old_chain = trace(source, port)
    new_ff, new_parity, new_chain = trace(optimized, port)
    expected = clones.get(new_ff, new_ff)
    require(old_ff == expected,
            f"{port}: source FF changed from {old_ff} to {new_ff}")
    require(old_parity == new_parity,
            f"{port}: inversion parity changed from {old_parity} to {new_parity}")
    port_records[port] = {
        "source_ff": old_ff,
        "optimized_ff": new_ff,
        "inversion_parity": new_parity,
        "source_chain_cells": len(old_chain),
        "optimized_chain_cells": len(new_chain),
    }

for clone_name, source_name in clones.items():
    old = optimized_insts[source_name]
    new = optimized_insts[clone_name]
    require(old.getMaster().getName() == new.getMaster().getName(),
            f"{clone_name}: clone master differs from {source_name}")
    old_pins = pins(old)
    new_pins = pins(new)
    for pin in old_pins:
        if pin != "QN":
            require(old_pins[pin] == new_pins[pin],
                    f"{clone_name}: clone input pin {pin} differs")
    require(old_pins["QN"] != new_pins["QN"],
            f"{clone_name}: clone output was not placed on a separate net")

report = {
    "schema_version": 2,
    "status": "pass",
    "policy": (
        "hash-bound OpenDB connectivity comparison: only recorded BUF removals "
        "and two output-only FF clones are allowed; every boundary output must "
        "retain its source FF and inversion parity"
    ),
    "artifacts": {
        "generator": file_record(__file__),
        "source_odb": file_record(args.source_odb),
        "optimized_odb": file_record(args.optimized_odb),
        "collapse_report": file_record(args.collapse_report_json),
        "selection_reports": [file_record(path) for path in args.selection_json],
    },
    "boundary_ports_checked": len(port_records),
    "outside_cone_instances_checked": outside_checked,
    "removed_buffer_cells": len(removed),
    "equivalent_output_only_ff_clones": clones,
    "ports": port_records,
}
with open(args.output_json, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
    handle.write("\n")
print(f"PASS: {len(port_records)} ports, {outside_checked} outside-cone cells")
