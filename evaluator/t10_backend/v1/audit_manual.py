"""Prove an exact net-local geometry change, preserving logic and placement."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import odb

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'physical'))
from t10_manual_v15_audit import read_snapshot


def artifact(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024**2),b''):
            digest.update(chunk)
    return dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=digest.hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path)
    parser.add_argument('after',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--changed-net',action='append',required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('audit output exists; do not overwrite')
    before,after=[read_snapshot(str(path)) for path in (args.before,args.after)]
    invariants=('logical','placements','masters','obstructions','bterms')
    if any(before[key]!=after[key] for key in invariants) or before['routes'].keys()!=after['routes'].keys():
        raise ValueError('logic, placement, library, obstruction or terminal changed')
    changed=sorted(net for net in before['routes'] if before['routes'][net]!=after['routes'][net])
    if changed!=sorted(args.changed_net):
        raise ValueError('unexpected changed routes: '+repr(changed))
    database=odb.dbDatabase.create(); odb.read_db(database,str(args.after))
    vias=[]
    for via in database.getChip().getBlock().getVias():
        if not via.getName().startswith('T10_'):
            continue
        boxes=list(via.getBoxes())
        metals=[box for box in boxes if box.getTechLayer().getName().startswith('M')]
        cuts=[box for box in boxes if box.getTechLayer().getName().startswith('V')]
        if len(metals)!=2 or not cuts or any(not (metal.xMin()<=cut.xMin() and metal.yMin()<=cut.yMin()
                and metal.xMax()>=cut.xMax() and metal.yMax()>=cut.yMax()) for metal in metals for cut in cuts):
            raise ValueError('custom via does not fully cover its cut: '+via.getName())
        vias.append(via.getName())
    result=dict(status='passed',nets_checked=len(before['routes']),changed_nets=changed,
                invariant_sha256={key:before[key] for key in invariants},
                custom_vias_with_full_cut_coverage=vias,
                before=artifact(args.before),after=artifact(args.after),checker=artifact(Path(__file__)))
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('MANUAL INVARIANTS PASSED',result['nets_checked'],'nets; changed only',changed)


if __name__=='__main__':
    main()
