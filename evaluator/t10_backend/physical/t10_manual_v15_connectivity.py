"""Geometric connectivity audit for only the five manually edited v15 nets.

Run with OpenROAD's Python interpreter, passing original and patched ODB paths.
Join overlapping metal rectangles and each via/pin's shapes, then require a
single component containing every routed shape and every logical terminal.
"""
import json
import sys

import odb

from t10_manual_v15_inspect import transform_rect, wire_shapes

NETS = ["net24982", r"level0\[4\]\[314\]", "net22071",
        r"quad_sum\[0\]\[355\]", r"quad_sum\[1\]\[366\]"]


def audit(path):
    db = odb.dbDatabase.create()
    odb.read_db(db, path)
    block = db.getChip().getBlock()
    results = []
    for name in NETS:
        net = block.findNet(name)
        if net is None:
            raise RuntimeError(f"missing net {name}")
        shapes = list(wire_shapes(net))
        for item in shapes:
            if item["kind"] == "route_via":
                # All enclosure/cut boxes belonging to this via are connected.
                item["group"] = ("via", item["via"], *item["origin"])
        terminals = []
        for iterm in net.getITerms():
            inst = iterm.getInst()
            term = f"{inst.getName()}/{iterm.getMTerm().getName()}"
            terminals.append(term)
            for mpin in iterm.getMTerm().getMPins():
                for box in mpin.getGeometry():
                    layer = box.getTechLayer()
                    if layer is not None:
                        shapes.append(dict(layer=layer.getName(),
                                           bbox=transform_rect(inst.getTransform(), box),
                                           group=("pin", term)))
        for bterm in net.getBTerms():
            term = bterm.getName()
            terminals.append(term)
            for pin in bterm.getBPins():
                for box in pin.getBoxes():
                    shapes.append(dict(layer=box.getTechLayer().getName(),
                                       bbox=(box.xMin(), box.yMin(), box.xMax(), box.yMax()),
                                       group=("pin", term)))
        parent = list(range(len(shapes)))

        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def join(i, j):
            parent[root(i)] = root(j)

        for i, a in enumerate(shapes):
            for j in range(i):
                b = shapes[j]
                if a.get("group") is not None and a.get("group") == b.get("group"):
                    join(i, j)
                elif a["layer"] == b["layer"]:
                    x, y = a["bbox"], b["bbox"]
                    if x[0] <= y[2] and y[0] <= x[2] and x[1] <= y[3] and y[1] <= x[3]:
                        join(i, j)
        components = len({root(i) for i in range(len(shapes))})
        covered = {s["group"][1] for s in shapes if s.get("group", (None,))[0] == "pin"}
        result = dict(net=name, shapes=len(shapes), terminals=len(terminals),
                      components=components, all_terminals_have_geometry=set(terminals) == covered)
        results.append(result)
        if components != 1 or not result["all_terminals_have_geometry"]:
            raise RuntimeError(json.dumps(result))
    print(json.dumps(dict(odb=path, nets=results), sort_keys=True))


if __name__ == "__main__":
    for odb_path in sys.argv[1:]:
        audit(odb_path)
