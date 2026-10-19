"""Assert that the manual patch changes only five routed nets and local vias."""
import hashlib
import json
import sys
import odb
from t10_manual_v15_inspect import wire_shapes
from t10_manual_v15_connectivity import NETS


def digest(rows):
    value = hashlib.sha256()
    for row in rows:
        value.update(repr(row).encode())
        value.update(b"\n")
    return value.hexdigest()


def read_snapshot(path):
    db = odb.dbDatabase.create()
    odb.read_db(db, path)
    block = db.getChip().getBlock()
    routes, logical = {}, []
    for net in block.getNets():
        routes[net.getName()] = digest(
            (s["kind"], s["layer"], s["bbox"], s.get("via"), s.get("origin"))
            for s in wire_shapes(net))
        logical.append((net.getName(), str(net.getSigType()),
                        sorted((t.getInst().getName(), t.getMTerm().getName()) for t in net.getITerms()),
                        sorted(t.getName() for t in net.getBTerms())))
    placements = digest((i.getName(), i.getMaster().getName(), i.getLocation(),
                         str(i.getOrient()), str(i.getPlacementStatus())) for i in block.getInsts())
    masters = []
    for lib in db.getLibs():
        for master in lib.getMasters():
            boxes = [(b.getTechLayer().getName(), b.xMin(), b.yMin(), b.xMax(), b.yMax())
                     for b in master.getObstructions() if b.getTechLayer()]
            pins = [(t.getName(), [(b.getTechLayer().getName(),b.xMin(),b.yMin(),b.xMax(),b.yMax())
                                   for pin in t.getMPins() for b in pin.getGeometry() if b.getTechLayer()])
                    for t in master.getMTerms()]
            masters.append((lib.getName(),master.getName(),master.getWidth(),master.getHeight(),boxes,pins))
    obstructions = []
    for obstruction in block.getObstructions():
        b = obstruction.getBBox()
        obstructions.append((b.getTechLayer().getName(),b.xMin(),b.yMin(),b.xMax(),b.yMax()))
    bterms = [(t.getName(),[(b.getTechLayer().getName(),b.xMin(),b.yMin(),b.xMax(),b.yMax())
                           for p in t.getBPins() for b in p.getBoxes()]) for t in block.getBTerms()]
    for via in block.getVias():
        boxes = list(via.getBoxes())
        metals = [b for b in boxes if b.getTechLayer().getName().startswith("M")]
        cuts = [b for b in boxes if b.getTechLayer().getName().startswith("V")]
        if via.getName().startswith("T10_V15_"):
            assert len(metals)==2 and len(cuts)==1, via.getName()
            for metal in metals:
                for cut in cuts:
                    assert (metal.xMin()<=cut.xMin() and metal.yMin()<=cut.yMin()
                            and metal.xMax()>=cut.xMax() and metal.yMax()>=cut.yMax()), via.getName()
    state = dict(logical=digest(logical),placements=placements,masters=digest(masters),
                 obstructions=digest(obstructions),bterms=digest(bterms),routes=routes)
    odb.dbDatabase.destroy(db)
    return state


if __name__ == "__main__":
    before, after = [read_snapshot(p) for p in sys.argv[1:3]]
    for invariant in ("logical","placements","masters","obstructions","bterms"):
        assert before[invariant] == after[invariant], invariant
    assert set(before["routes"]) == set(after["routes"])
    changed = sorted(n for n in before["routes"] if before["routes"][n] != after["routes"][n])
    assert changed == sorted(NETS), changed
    print(json.dumps(dict(status="passed",nets_checked=len(before["routes"]),changed_nets=changed,
                          invariant_sha256={k:v for k,v in before.items() if k!="routes"}),sort_keys=True))
