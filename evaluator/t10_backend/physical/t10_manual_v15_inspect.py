#!/usr/bin/env python3
"""Inspect routed and fixed geometry around the five frozen v15 PE DRC markers."""

import argparse
import json

import odb


MARKERS_UM = [
    ("M2", (365.027, 278.172, 365.040, 278.190)),
    ("M3", (210.816, 406.440, 210.834, 406.453)),
    ("M4", (209.939, 176.352, 210.000, 176.376)),
    ("M5", (133.728, 413.943, 133.752, 414.005)),
    ("M6", (316.408, 310.848, 316.469, 310.880)),
]


def bbox_tuple(box):
    return (box.xMin(), box.yMin(), box.xMax(), box.yMax())


def gap(lhs, rhs):
    dx = max(rhs[0] - lhs[2], lhs[0] - rhs[2], 0)
    dy = max(rhs[1] - lhs[3], lhs[1] - rhs[3], 0)
    return max(dx, dy)


def transform_rect(transform, box):
    first = odb.Point(box.xMin(), box.yMin())
    second = odb.Point(box.xMax(), box.yMax())
    transform.apply(first)
    transform.apply(second)
    return (
        min(first.x(), second.x()),
        min(first.y(), second.y()),
        max(first.x(), second.x()),
        max(first.y(), second.y()),
    )


def wire_shapes(net):
    wire = net.getWire()
    if wire is None:
        return
    iterator = odb.dbWirePathItr()
    path = odb.dbWirePath()
    shape = odb.dbWirePathShape()
    iterator.begin(wire)
    while iterator.getNextPath(path):
        while iterator.getNextShape(shape):
            obj = shape.shape
            if obj.isVia():
                x, y = obj.getViaXY()
                via = obj.getTechVia() or obj.getVia()
                for box in via.getBoxes():
                    layer = box.getTechLayer()
                    if layer is None:
                        continue
                    yield {
                        "kind": "route_via",
                        "net": net.getName(),
                        "layer": layer.getName(),
                        "bbox": (
                            box.xMin() + x,
                            box.yMin() + y,
                            box.xMax() + x,
                            box.yMax() + y,
                        ),
                        "via": via.getName(),
                        "origin": (x, y),
                    }
            else:
                layer = obj.getTechLayer()
                if layer is None:
                    continue
                yield {
                    "kind": "route_segment",
                    "net": net.getName(),
                    "layer": layer.getName(),
                    "bbox": bbox_tuple(obj.getBox()),
                }


def fixed_shapes(inst):
    transform = inst.getTransform()
    master = inst.getMaster()
    for box in master.getObstructions():
        layer = box.getTechLayer()
        if layer is not None:
            yield {
                "kind": "macro_obstruction",
                "instance": inst.getName(),
                "master": master.getName(),
                "layer": layer.getName(),
                "bbox": transform_rect(transform, box),
            }
    net_by_mterm = {
        iterm.getMTerm().getName(): (
            iterm.getNet().getName() if iterm.getNet() is not None else None
        )
        for iterm in inst.getITerms()
    }
    for mterm in master.getMTerms():
        for mpin in mterm.getMPins():
            for box in mpin.getGeometry():
                layer = box.getTechLayer()
                if layer is not None:
                    yield {
                        "kind": "macro_pin",
                        "instance": inst.getName(),
                        "master": master.getName(),
                        "terminal": mterm.getName(),
                        "net": net_by_mterm.get(mterm.getName()),
                        "layer": layer.getName(),
                        "bbox": transform_rect(transform, box),
                    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("odb")
    parser.add_argument("output")
    parser.add_argument("--halo-nm", type=int, default=250)
    parser.add_argument("--all-layers", action="store_true")
    args = parser.parse_args()

    database = odb.dbDatabase.create()
    odb.read_db(database, args.odb)
    block = database.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()
    markers = [
        {
            "layer": layer,
            "bbox": tuple(round(value * dbu) for value in box),
        }
        for layer, box in MARKERS_UM
    ]
    halo = round(args.halo_nm * dbu / 1000)
    records = []
    for index, marker in enumerate(markers, start=1):
        record = {"index": index, **marker, "halo_dbu": halo, "shapes": []}
        records.append(record)

    for net in block.getNets():
        for shape in wire_shapes(net):
            for record in records:
                if (args.all_layers or shape["layer"] == record["layer"]) and gap(shape["bbox"], record["bbox"]) <= halo:
                    item = dict(shape)
                    item["gap_dbu"] = gap(shape["bbox"], record["bbox"])
                    record["shapes"].append(item)

    for inst in block.getInsts():
        for shape in fixed_shapes(inst):
            for record in records:
                if (args.all_layers or shape["layer"] == record["layer"]) and gap(shape["bbox"], record["bbox"]) <= halo:
                    item = dict(shape)
                    item["gap_dbu"] = gap(shape["bbox"], record["bbox"])
                    record["shapes"].append(item)

    for record in records:
        record["shapes"].sort(
            key=lambda item: (item["gap_dbu"], item["kind"], item.get("net", ""))
        )
        print(
            f"MARKER {record['index']} {record['layer']} {record['bbox']} "
            f"shapes={len(record['shapes'])}"
        )
        for item in record["shapes"]:
            print(json.dumps(item, sort_keys=True))

    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "odb": args.odb,
                "dbu_per_micron": dbu,
                "records": records,
            },
            stream,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")


if __name__ == "__main__":
    main()
