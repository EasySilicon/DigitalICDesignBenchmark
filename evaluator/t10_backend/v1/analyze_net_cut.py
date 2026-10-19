"""Read-only topology study of removing a bounded local route fragment."""
import argparse
from collections import Counter
from pathlib import Path
import sys

import odb

from full_geometry import wire_shapes
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'physical'))
from t10_manual_v15_inspect import transform_rect


def labels(shapes):
    parent=list(range(len(shapes)))
    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]; i=parent[i]
        return i
    groups={}; layers={}
    for i,shape in enumerate(shapes):
        group=shape.get('group')
        if group is not None:
            if group in groups: parent[root(i)]=root(groups[group])
            else: groups[group]=i
        layers.setdefault(shape['layer'],[]).append(i)
    for indices in layers.values():
        active=[]
        for i in sorted(indices,key=lambda j:shapes[j]['bbox'][0]):
            x0,y0,x1,y1=shapes[i]['bbox']
            active=[j for j in active if shapes[j]['bbox'][2]>=x0]
            for j in active:
                _,a0,_,a1=shapes[j]['bbox']
                if y0<=a1 and a0<=y1: parent[root(i)]=root(j)
            active.append(i)
    return [root(i) for i in range(len(shapes))]


parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('odb'); parser.add_argument('net'); parser.add_argument('box')
args=parser.parse_args(); box=tuple(map(int,args.box.split(',')))
database=odb.dbDatabase.create(); odb.read_db(database,args.odb)
net=database.getChip().getBlock().findNet(args.net)
if not net: raise ValueError('net missing')
shapes=list(wire_shapes(net))
for shape in shapes:
    if shape['kind']=='route_via': shape['group']=('via',shape['via'],*shape['origin'])
for terminal in net.getITerms():
    inst=terminal.getInst(); name=inst.getName()+'/'+terminal.getMTerm().getName()
    for pin in terminal.getMTerm().getMPins():
        for rect in pin.getGeometry():
            if rect.getTechLayer():
                shapes.append(dict(kind='pin',layer=rect.getTechLayer().getName(),
                                   bbox=transform_rect(inst.getTransform(),rect),group=('pin',name)))
before=len(set(labels(shapes)))
removed=[]; kept=[]
for shape in shapes:
    x0,y0,x1,y1=shape['bbox']
    selected=shape['kind']!='pin' and x0>=box[0] and y0>=box[1] and x1<=box[2] and y1<=box[3]
    (removed if selected else kept).append(shape)
roots=labels(kept)
print('CUT STUDY',net.getName(),'before',before,'after',len(set(roots)),
      'removed',dict(Counter((s['kind'],s['layer']) for s in removed)))
for root in sorted(set(roots)):
    part=[shape for i,shape in enumerate(kept) if roots[i]==root]
    pins=sorted({shape['group'][1] for shape in part if shape['kind']=='pin'})
    bound=[min(s['bbox'][0] for s in part),min(s['bbox'][1] for s in part),
           max(s['bbox'][2] for s in part),max(s['bbox'][3] for s in part)]
    print('COMPONENT',len(part),'shapes',len(pins),'pins',bound,pins[:4])
