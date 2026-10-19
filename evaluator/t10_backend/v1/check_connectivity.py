"""Read-only geometric connectivity audit of every signal net in final ODB.

Join same-layer touching/overlapping metal, all layers of each actual via,
and shapes belonging to one logical pin. Require every routed shape and all
logical terminals of each signal net to lie in a single connected component.
No detailed-router live-state assumptions and no routing or database writes.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys


def components(shapes):
    parent = list(range(len(shapes)))
    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index
    def join(left,right):
        parent[root(left)] = root(right)
    groups, layers = {}, defaultdict(list)
    for i,shape in enumerate(shapes):
        group=shape.get("group")
        if group is not None:
            if group in groups:
                join(i,groups[group])
            else:
                groups[group]=i
        layers[shape["layer"]].append(i)
    for indices in layers.values():
        active=[]
        for i in sorted(indices,key=lambda k:shapes[k]["bbox"][0]):
            x0,y0,x1,y1=shapes[i]["bbox"]
            active=[j for j in active if shapes[j]["bbox"][2]>=x0]
            for j in active:
                _,a0,_,a1=shapes[j]["bbox"]
                if y0<=a1 and a0<=y1:
                    join(i,j)
            active.append(i)
    return len({root(i) for i in range(len(shapes))})


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024**2),b''):
            digest.update(chunk)
    return digest.hexdigest()


def audit(path,output):
    import odb
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'physical'))
    from t10_manual_v15_inspect import transform_rect, wire_shapes
    database=odb.dbDatabase.create()
    odb.read_db(database,str(path))
    block=database.getChip().getBlock()
    checked=skipped_power=total_shapes=total_terminals=0
    failures=[]
    for net in block.getNets():
        if str(net.getSigType()) in ('POWER','GROUND'):
            skipped_power+=1
            continue
        shapes=list(wire_shapes(net))
        for shape in shapes:
            if shape['kind']=='route_via':
                shape['group']=('via',shape['via'],*shape['origin'])
        terminals=[]
        for iterm in net.getITerms():
            inst=iterm.getInst()
            name=inst.getName()+'/'+iterm.getMTerm().getName()
            terminals.append(name)
            for mpin in iterm.getMTerm().getMPins():
                for box in mpin.getGeometry():
                    layer=box.getTechLayer()
                    if layer is not None:
                        shapes.append(dict(layer=layer.getName(),bbox=transform_rect(inst.getTransform(),box),group=('pin',name)))
        for bterm in net.getBTerms():
            name='PORT:'+bterm.getName()
            terminals.append(name)
            for pin in bterm.getBPins():
                for box in pin.getBoxes():
                    shapes.append(dict(layer=box.getTechLayer().getName(),bbox=(box.xMin(),box.yMin(),box.xMax(),box.yMax()),group=('pin',name)))
        count=components(shapes)
        covered={s['group'][1] for s in shapes if s.get('group',(None,))[0]=='pin'}
        if count!=1 or covered!=set(terminals):
            failures.append(dict(net=net.getName(),components=count,shapes=len(shapes),terminals=len(terminals),missing_terminal_geometry=sorted(set(terminals)-covered)))
        checked+=1
        total_shapes+=len(shapes)
        total_terminals+=len(terminals)
        if checked%5000==0:
            print(f'CHECKED {checked} signal nets; failures={len(failures)}',flush=True)
    result=dict(status='passed' if checked and not failures else 'failed',
                method='whole_database_geometric_signal_net_connectivity',
                odb=dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path)),
                signal_nets_checked=checked,power_ground_nets_excluded=skipped_power,
                shapes_checked=total_shapes,terminals_checked=total_terminals,
                failures=failures,checker_sha256=sha(Path(__file__)))
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='failures'}),flush=True)
    if failures or not checked:
        raise RuntimeError(f'{len(failures)} signal nets failed geometric connectivity; see {output}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('odb',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    audit(args.odb,args.output)
