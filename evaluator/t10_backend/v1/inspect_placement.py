"""Read-only inspection of a named cell and its physical placement region."""
import json
import sys

import odb


def rect(box):
    return [box.xMin(), box.yMin(), box.xMax(), box.yMax()]


database = odb.dbDatabase.create()
odb.read_db(database, sys.argv[1])
block = database.getChip().getBlock()
selected = block.findInst(sys.argv[2])
matches = [selected] if selected else []
for inst in matches:
    box = inst.getBBox()
    group = inst.getGroup()
    region = group.getRegion() if group else None
    nearby = []
    for other in block.getInsts():
        other_box = other.getBBox()
        if (other != inst and other_box.xMin() < box.xMax() + 2000
                and other_box.xMax() > box.xMin() - 2000
                and other_box.yMin() < box.yMax() + 1000
                and other_box.yMax() > box.yMin() - 1000):
            nearby.append(dict(name=other.getName(), bbox=rect(other_box)))
    print(json.dumps(dict(name=inst.getName(), master=inst.getMaster().getName(),
                         location=list(inst.getLocation()), orientation=str(inst.getOrient()),
                         bbox=rect(box), group=group.getName() if group else None,
                         region=region.getName() if region else None,
                         boundaries=[rect(boundary) for boundary in region.getBoundaries()] if region else [],
                         nearby=nearby), indent=2))
if not matches:
    raise ValueError('no matching cell')
