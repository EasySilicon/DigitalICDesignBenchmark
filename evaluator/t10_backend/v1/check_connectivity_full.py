"""Supplement historical connectivity checks with complete RECT-aware geometry."""
import argparse
import json
from pathlib import Path
import sys

import odb

from check_connectivity import components, sha
from full_geometry import POLICY, wire_shapes
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'physical'))
from t10_manual_v15_inspect import transform_rect


def audit(path,output):
    database=odb.dbDatabase.create(); odb.read_db(database,str(path))
    block=database.getChip().getBlock()
    checked=skipped=total_shapes=total_terminals=0; failures=[]
    for net in block.getNets():
        if str(net.getSigType()) in ('POWER','GROUND'):
            skipped+=1; continue
        shapes=list(wire_shapes(net))
        for shape in shapes:
            if shape['kind']=='route_via':
                shape['group']=('via',shape['via'],*shape['origin'])
        terminals=[]
        for terminal in net.getITerms():
            inst=terminal.getInst(); name=inst.getName()+'/'+terminal.getMTerm().getName()
            terminals.append(name)
            for pin in terminal.getMTerm().getMPins():
                for box in pin.getGeometry():
                    if box.getTechLayer() is not None:
                        shapes.append(dict(layer=box.getTechLayer().getName(),
                                           bbox=transform_rect(inst.getTransform(),box),group=('pin',name)))
        for terminal in net.getBTerms():
            name='PORT:'+terminal.getName(); terminals.append(name)
            for pin in terminal.getBPins():
                for box in pin.getBoxes():
                    shapes.append(dict(layer=box.getTechLayer().getName(),
                                       bbox=(box.xMin(),box.yMin(),box.xMax(),box.yMax()),group=('pin',name)))
        count=components(shapes)
        covered={shape['group'][1] for shape in shapes if shape.get('group',(None,))[0]=='pin'}
        if count!=1 or covered!=set(terminals):
            failures.append(dict(net=net.getName(),components=count,shapes=len(shapes),terminals=len(terminals),
                                 missing_terminal_geometry=sorted(set(terminals)-covered)))
        checked+=1; total_shapes+=len(shapes); total_terminals+=len(terminals)
        if checked%5000==0:
            print('FULL GEOMETRY CHECKED',checked,'signal nets; failures',len(failures),flush=True)
    result=dict(status='passed' if checked and not failures else 'failed',
                method='whole_database_geometric_signal_net_connectivity',wire_iterator_policy=POLICY,
                odb=dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path)),
                signal_nets_checked=checked,power_ground_nets_excluded=skipped,shapes_checked=total_shapes,
                terminals_checked=total_terminals,failures=failures,checker_sha256=sha(Path(__file__)),
                iterator_sha256=sha(Path(__file__).with_name('full_geometry.py')),
                union_algorithm_sha256=sha(Path(__file__).with_name('check_connectivity.py')))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print('FULL GEOMETRY',result['status'],checked,'nets',total_shapes,'shapes',flush=True)
    if failures or not checked:
        raise ValueError('full geometry connectivity failed: '+str(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('odb',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args(); audit(args.odb,args.output)
