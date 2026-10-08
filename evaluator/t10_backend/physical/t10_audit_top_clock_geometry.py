"""Audit all clock branches in the complete 16x16 physical top, without edits.

Run through OpenROAD -python; geometrical distance is diagnostic, not STA.
"""
import argparse
import json
from pathlib import Path


def center(box):
    return [(box.xMin() + box.xMax()) / 2,
            (box.yMin() + box.yMax()) / 2]


def main():
    import odb

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_odb")
    p.add_argument("output_json")
    args = p.parse_args()
    db = odb.dbDatabase.create()
    odb.read_db(db, args.input_odb)
    block = db.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()
    macros = [i for i in block.getInsts() if i.getMaster().isBlock()]
    if len(macros) != 16:
        raise RuntimeError(f"Expected 16 tile macros, got {len(macros)}")
    branches = []
    clock_nets = 0
    for net in block.getNets():
        if str(net.getSigType()) != "CLOCK":
            continue
        clock_nets += 1
        drivers = [t for t in net.getITerms()
                   if str(t.getIoType()) == "OUTPUT"]
        if len(drivers) != 1:
            continue  # Primary input clock; explicitly not a cell-driven branch.
        driver = drivers[0]
        dxy = center(driver.getBBox())
        inputs = [t for t in net.getITerms()
                  if str(t.getIoType()) == "INPUT"]
        for sink in inputs:
            sxy = center(sink.getBBox())
            distance = sum(abs(a - b) for a, b in zip(dxy, sxy)) / dbu
            if distance < 150:
                continue
            branches.append({"net": net.getName(),
                             "driver": driver.getInst().getName(),
                             "driver_pin": driver.getMTerm().getName(),
                             "driver_xy_um": [x / dbu for x in dxy],
                             "sink": sink.getInst().getName(),
                             "sink_pin": sink.getMTerm().getName(),
                             "sink_master": sink.getInst().getMaster().getName(),
                             "sink_xy_um": [x / dbu for x in sxy],
                             "manhattan_um": distance,
                             "fanout": len(inputs),
                             "wide_ndr": net.getNonDefaultRule() is not None})
    branches.sort(key=lambda b: (-b["manhattan_um"], b["net"], b["sink"]))
    counts = {str(limit): sum(b["manhattan_um"] > limit for b in branches)
              for limit in (150, 300, 500, 1000, 2000)}
    report = {"diagnostic_only": True, "input_odb": args.input_odb,
              "instance_count": len(block.getInsts()), "tile_macros": 16,
              "pe_instances_by_hierarchy": 256, "clock_nets": clock_nets,
              "long_branches_by_threshold_um": counts,
              "maximum_branch_um": branches[0]["manhattan_um"] if branches else 0,
              "branches": branches}
    Path(args.output_json).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "branches"}))
    for b in branches[:12]:
        print(json.dumps(b))


if __name__ == "__main__":
    main()
