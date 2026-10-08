"""Place existing output-control repeaters along actual full-top channels.

Only combinational positive buffers move. Connectivity, clock trees,
registers and macros remain byte-for-byte equivalent as ODB properties.
"""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from t10_repair_top_clock_channels import Channels, NewCellPlacer, distance, xy


def immutable_snapshot(block, movable):
    h=hashlib.sha256()
    for inst in sorted(block.getInsts(),key=lambda i:i.getName()):
        h.update(repr((inst.getName(),inst.getMaster().getName())).encode())
        if inst.getName() not in movable:
            h.update(repr((inst.getLocation(),str(inst.getOrient()),str(inst.getPlacementStatus()))).encode())
        for pin in sorted(inst.getITerms(),key=lambda p:p.getMTerm().getName()):
            net=pin.getNet()
            h.update(repr((pin.getMTerm().getName(),net.getName() if net else None)).encode())
    return h.hexdigest()


def point_at(path, progress):
    for a,b in zip(path,path[1:]):
        length=distance(a,b)
        if progress <= length:
            return (a[0]+(1 if b[0]>a[0] else -1 if b[0]<a[0] else 0)*progress,
                    a[1]+(1 if b[1]>a[1] else -1 if b[1]<a[1] else 0)*progress)
        progress-=length
    return path[-1]


def main():
    import odb
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input_odb')
    p.add_argument('output_odb')
    p.add_argument('report_json')
    args=p.parse_args()
    db=odb.dbDatabase.create();odb.read_db(db,args.input_odb)
    block=db.getChip().getBlock();dbu=block.getDbUnitsPerMicron()
    macros=[i for i in block.getInsts() if i.getMaster().isBlock()]
    assert len(macros)==16
    groups=defaultdict(list)
    for inst in block.getInsts():
        match=re.search(r't10_(finalpop|finalpush|writeptr)_s([0-3])c([0-9]+)r',inst.getName())
        if match:
            groups[(match[1],int(match[2]),int(match[3]))].append(inst)
    assert len(groups)==192
    movable={i.getName() for cells in groups.values() for i in cells}
    assert len(movable)==2304
    assert all(i.getMaster().getName()=='BUFx8_ASAP7_75t_R' for cells in groups.values() for i in cells)
    before=immutable_snapshot(block,movable)
    placer=NewCellPlacer(block,[i for i in block.getInsts() if not i.getMaster().isBlock() and i.getName() not in movable])
    channels=Channels(block,macros)
    chains=[]
    for key,cells in sorted(groups.items()):
        names={i.getName() for i in cells}
        drivers={i.getName():[pin for pin in i.findITerm('A').getNet().getITerms()
                             if str(pin.getIoType())=='OUTPUT'] for i in cells}
        assert all(len(v)==1 for v in drivers.values())
        first=[i for i in cells if drivers[i.getName()][0].getInst().getName() not in names]
        assert len(first)==1
        ordered=[];cursor=first[0]
        while cursor:
            assert cursor.getName() not in {i.getName() for i in ordered}
            ordered.append(cursor)
            successors=[t.getInst() for t in cursor.findITerm('Y').getNet().getITerms()
                        if str(t.getIoType())=='INPUT' and t.getInst().getName() in names]
            assert len(successors)<=1
            cursor=successors[0] if successors else None
        assert len(ordered)==12
        source=xy(drivers[first[0].getName()][0])
        loads=[t for t in ordered[-1].findITerm('Y').getNet().getITerms()
               if str(t.getIoType())=='INPUT']
        assert loads
        positions=[xy(t) for t in loads]
        median=(sorted(x[0] for x in positions)[len(positions)//2],
                sorted(x[1] for x in positions)[len(positions)//2])
        # An actual terminal is legal; a numerical median may lie in a macro.
        terminal=min(positions,key=lambda x:(distance(x,median),x))
        path=channels.route(channels.tree(source),terminal)
        length=sum(distance(a,b) for a,b in zip(path,path[1:]))
        moves=[]
        for index,inst in enumerate(ordered,1):
            target=point_at(path,round(length*index/(len(ordered)+1)))
            old=inst.getLocation()
            displacement=placer.place(inst,target)
            if displacement>75*dbu:
                raise RuntimeError(f'Cannot legally spread repeater within 75 um: {inst.getName()}')
            moves.append({'inst':inst.getName(),'old_xy':old,'new_xy':inst.getLocation(),
                          'target_displacement_um':displacement/dbu})
        branches=[]
        for inst in ordered:
            for net in (inst.findITerm('A').getNet(),inst.findITerm('Y').getNet()):
                roots=[t for t in net.getITerms() if str(t.getIoType())=='OUTPUT']
                assert len(roots)==1
                branches.extend(distance(xy(roots[0]),xy(t))/dbu for t in net.getITerms()
                                if str(t.getIoType())=='INPUT')
        chains.append({'control':key[0],'slot':key[1],'lane':key[2],
                       'route_um':length/dbu,'maximum_branch_manhattan_um':max(branches),'moves':moves})
    assert before==immutable_snapshot(block,movable)
    output=Path(args.output_odb);output.parent.mkdir(parents=True,exist_ok=True)
    odb.write_db(db,str(output))
    report={'diagnostic_only':True,'status':'placement_produced_pending_native_validation_and_routed_STA',
            'input_odb':args.input_odb,'tile_macros':16,'pe_count_by_hierarchy':256,
            'instance_count':len(block.getInsts()),'moved_existing_positive_buffers':len(movable),
            'control_chains':len(chains),'netlist_clock_and_register_geometry_unchanged':True,
            'immutable_properties_sha256':before,'maximum_chain_branch_um':max(c['maximum_branch_manhattan_um'] for c in chains),
            'chains':chains}
    Path(args.report_json).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='chains'}),flush=True)


if __name__=='__main__':
    main()
