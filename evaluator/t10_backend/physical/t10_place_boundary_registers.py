"""Place existing A/B boundary pipeline registers along their actual paths.

The netlist and all tile/gather/transport/I/O-buffer geometry are immutable.
Only named boundary registers and anonymous top combinational cells move.
This is a full-DUT diagnostic producer, never timing qualification.
"""
import argparse
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from t10_localize_gather_combinational import center, snapshot
from t10_place_top_port_buffers import port_point
from t10_repair_top_clock_channels import Channels, NewCellPlacer, xy, distance


def midpoint(points):
    return tuple(round(statistics.median(p[k] for p in points)) for k in (0,1))


def main():
    import odb
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('input_odb','output_odb','report_json'): p.add_argument(arg)
    args=p.parse_args(); started=time.monotonic()
    assert not Path(args.output_odb).exists()
    db=odb.dbDatabase.create(); odb.read_db(db,args.input_odb)
    block=db.getChip().getBlock(); dbu=block.getDbUnitsPerMicron()
    insts=list(block.getInsts()); macros=[i for i in insts if i.getMaster().isBlock()]
    assert len(macros)==16
    tiles={}
    for inst in macros:
        match=re.search(r'tile_row\[(\d)\]\.tile_col\[(\d)\]\.tile$',inst.getName().replace('\\',''))
        assert match; tiles[tuple(map(int,match.groups()))]=inst
    channels=Channels(block,macros)
    def project(point):
        return min([(x,point[1]) for x in channels.xs]+[(point[0],y) for y in channels.ys],
                   key=lambda q:(distance(point,q),q))
    def pin(axis,lane,kind,bit):
        tile=tiles[lane//4,0] if axis=='a' else tiles[0,lane//4]
        width=64 if kind=='data' else 28
        term=tile.findITerm(f'{axis}_in_{kind}[{(lane%4)*width+bit}]')
        assert term; return xy(term)
    def source(axis,lane,kind,bit):
        width=64 if kind=='data' else 16
        port=block.findBTerm(f'{axis}_{kind}[{lane*width+bit}]')
        assert port; return port_point(port)
    hard={}; families=Counter()
    for inst in insts:
        if not inst.getMaster().getName().startswith(('DFF','SDFF')): continue
        name=inst.getName().replace('\\','')
        match=re.match(r'([ab])_ctrl_(payload|valid)\[(\d+)\](?:\[(\d+)\])?',name)
        if match:
            axis,kind,lane,bit=match.groups(); lane=int(lane)
            target=pin(axis,lane,'token',27 if kind=='valid' else 16+int(bit))
            family=axis+'_control_spine'
        else:
            match=re.match(r'([ab])_(edge|skew)_(data|scale)\[(\d+)\]\[(\d+)\]',name)
            if match:
                axis,stage,kind,index,bit=match.groups(); index=int(index); bit=int(bit)
                lane=index if stage=='edge' else index//15
                step=1 if stage=='edge' else index%15+2
                assert lane<16 and step<=lane+1,(name,lane,step)
                a=source(axis,lane,kind,bit)
                b=pin(axis,lane,'data' if kind=='data' else 'token',bit)
                fraction=step/(lane+1)
                target=tuple(round(a[k]+fraction*(b[k]-a[k])) for k in (0,1))
                family=axis+'_'+stage+'_'+kind
            else:
                match=re.match(r'([ab])_scale_hold\[(\d+)\]\[(\d+)\]',name)
                if match:
                    axis,lane,bit=match.groups(); target=pin(axis,int(lane),'token',int(bit))
                    family=axis+'_scale_hold'
                else:
                    match=re.match(r'ingress_([ab])_(data|scale)\[(\d+)\]',name)
                    if not match: continue
                    axis,kind,index=match.groups(); index=int(index); width=64 if kind=='data' else 16
                    target=source(axis,index//width,kind,index%width)
                    family='ingress_'+axis+'_'+kind
        hard[inst.getName()]=project(target); families[family]+=1
    assert len(hard)>20000, families
    gates=[i for i in insts if re.fullmatch(r'_\d+_',i.getName())
           and not i.getMaster().getName().startswith(('DFF','SDFF','LATCH'))]
    moving={i.getName() for i in gates}|set(hard)
    immutable=snapshot(insts,moving)
    positions={i.getName():center(i) for i in insts}; before=dict(positions)
    positions.update(hard)
    neighbors=defaultdict(list); edges=[]
    for net in block.getNets():
        if str(net.getSigType())!='SIGNAL':continue
        loads=[t for t in net.getITerms() if str(t.getIoType())=='INPUT']
        if len(loads)>128 or any(t.getMTerm().getName() in ('SN','RN','RESETN','SETN','rst_n') for t in loads):continue
        roots=[t for t in net.getITerms() if str(t.getIoType())=='OUTPUT']
        if len(roots)!=1:continue
        root=roots[0]; a=root.getInst().getName()
        if root.getInst().getMaster().isBlock():
            a=('pin',a,root.getMTerm().getName()); positions[a]=xy(root);before[a]=positions[a]
        for t in loads:
            b=t.getInst().getName()
            if t.getInst().getMaster().isBlock():
                b=('pin',b,t.getMTerm().getName());positions[b]=xy(t);before[b]=positions[b]
            if a==b or a not in moving and b not in moving:continue
            edges.append((a,b));neighbors[a].append(b);neighbors[b].append(a)
    for iteration in range(12):
        for inst in gates if iteration%2==0 else reversed(gates):
            name=inst.getName()
            if neighbors[name]:positions[name]=project(midpoint([positions[n] for n in neighbors[name]]))
    placer=NewCellPlacer(block,[i for i in insts if not i.getMaster().isBlock() and i.getName() not in moving])
    cells=sorted((i for i in insts if i.getName() in moving),key=lambda i:(0 if i.getName() in hard else 1,
                                                                 -i.getMaster().getWidth(),i.getName()))
    maximum=0
    for n,inst in enumerate(cells):
        maximum=max(maximum,placer.place(inst,positions[inst.getName()])/dbu)
        positions[inst.getName()]=center(inst)
        if n%10000==0:print(f'T10_BOUNDARY_LOCALITY placed={n}/{len(cells)}',flush=True)
    assert snapshot(insts,moving)==immutable
    lengths=lambda pos:[distance(pos[a],pos[b])/dbu for a,b in edges]
    old,new=lengths(before),lengths(positions)
    odb.write_db(db,args.output_odb)
    report={'diagnostic_only':True,'physical_qualification_passed':False,'tile_macros':16,
            'instance_count':len(insts),'moved_boundary_registers':len(hard),'families':dict(families),
            'moved_top_combinational_cells':len(gates),'immutable_netlist_helper_macro_io_geometry_sha256':immutable,
            'netlist_and_helper_macro_io_geometry_unchanged':True,'related_driver_load_branches':len(edges),
            'driver_load_manhattan_sum_before_um':sum(old),'driver_load_manhattan_sum_after_um':sum(new),
            'maximum_related_branch_before_um':max(old),'maximum_related_branch_after_um':max(new),
            'maximum_legal_target_displacement_um':maximum,'elapsed_seconds':time.monotonic()-started}
    Path(args.report_json).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
