"""Read-only complete route geometry of one exactly named net."""
import json
from pathlib import Path
import sys

import odb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'physical'))
from t10_manual_v15_inspect import gap
from full_geometry import wire_shapes

database = odb.dbDatabase.create()
odb.read_db(database, sys.argv[1])
block = database.getChip().getBlock()
net = block.findNet(sys.argv[2])
if not net or not net.getWire():
    raise ValueError('missing routed net')
print('NET', net.getName(), 'wire_length', net.getWire().length())
window=tuple(map(int,sys.argv[3].split(','))) if len(sys.argv)>3 else None
for shape in wire_shapes(net):
    if window and gap(shape['bbox'],window)>0:
        continue
    print(json.dumps(shape, separators=(',',':')))
