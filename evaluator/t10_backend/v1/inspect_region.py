"""Read-only local geometry for a hand-designed ECO; this is not a DRC report."""
import argparse
import json
from pathlib import Path
import sys

import odb

from full_geometry import POLICY,wire_shapes
from special_geometry import special_shapes
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'physical'))
from t10_manual_v15_inspect import fixed_shapes,gap

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('odb'); parser.add_argument('output',type=Path)
parser.add_argument('box',help='xmin,ymin,xmax,ymax in database units')
args=parser.parse_args()
if args.output.exists():
    raise ValueError('inspection output exists')
box=tuple(map(int,args.box.split(',')))
database=odb.dbDatabase.create(); odb.read_db(database,args.odb)
block=database.getChip().getBlock(); shapes=[]
for net in block.getNets():
    shapes.extend(shape for shape in wire_shapes(net) if gap(shape['bbox'],box)==0)
    shapes.extend(shape for shape in special_shapes(net,region=box) if gap(shape['bbox'],box)==0)
for inst in block.getInsts():
    shapes.extend(shape for shape in fixed_shapes(inst) if gap(shape['bbox'],box)==0)
args.output.write_text(json.dumps(dict(method='local_geometry_inspection_not_DRC',odb=args.odb,special_routes_included=True,
                                      region=box,wire_iterator_policy=POLICY,shapes=shapes),indent=2)+'\n')
print('INSPECTED',len(shapes),'local shapes; no database mutation')
