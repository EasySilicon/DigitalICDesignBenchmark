"""Record full-DUT geometry and cell footprint; never a PPA release receipt."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from t10_repair_top_clock_channels import distance, xy
from t10_place_top_port_buffers import port_point


def main():
    import odb
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input_odb');p.add_argument('report_json');args=p.parse_args()
    db=odb.dbDatabase.create();odb.read_db(db,args.input_odb)
    block=db.getChip().getBlock();dbu=block.getDbUnitsPerMicron()
    insts=list(block.getInsts());macros=[i for i in insts if i.getMaster().isBlock()]
    if len(macros)!=16:raise RuntimeError('Require the full sixteen-tile DUT')
    area=lambda i:i.getMaster().getWidth()*i.getMaster().getHeight()/(dbu*dbu)
    counts={'SIGNAL':Counter(),'CLOCK':Counter()};maximum={};skipped=Counter()
    for net in block.getNets():
        kind=str(net.getSigType())
        if kind not in counts:continue
        roots=[t for t in net.getITerms() if str(t.getIoType())=='OUTPUT']
        sources=[(xy(t),t.getInst().getName()+'/'+t.getMTerm().getName()) for t in roots]
        sources += [(port_point(t),'port:'+t.getName()) for t in net.getBTerms() if str(t.getIoType())=='INPUT']
        if len(sources)!=1:skipped[kind+'_not_one_source']+=1;continue
        loads=[t for t in net.getITerms() if str(t.getIoType())=='INPUT']
        if kind=='SIGNAL' and any(t.getMTerm().getName() in ('RESETN','SETN','RN','SN','rst_n') for t in loads):
            skipped['reset_or_constant_control']+=1;continue
        sinks=[(xy(t),t.getInst().getName()+'/'+t.getMTerm().getName()) for t in loads]
        sinks += [(port_point(t),'port:'+t.getName()) for t in net.getBTerms() if str(t.getIoType())=='OUTPUT']
        for point,name in sinks:
            length=distance(sources[0][0],point)/dbu
            counts[kind]['total_branches']+=1
            for threshold in (300,500,1000,2000):
                if length>threshold:counts[kind][f'above_{threshold}_um']+=1
            if length>maximum.get(kind,{}).get('manhattan_um',-1):
                maximum[kind]={'manhattan_um':length,'net':net.getName(),
                               'driver':sources[0][1],'sink':name}
    port_h=hashlib.sha256()
    for port in sorted(block.getBTerms(),key=lambda t:t.getName()):
        port_h.update(repr((port.getName(),str(port.getIoType()),port_point(port),port.getNet().getName())).encode())
    result={'diagnostic_only':True,'ppa_baseline_qualified':False,'input_odb':args.input_odb,
            'tile_macros':16,'pe_count_by_hierarchy':256,'instance_count':len(insts),
            'standard_cell_count':len(insts)-len(macros),
            'macro_lef_footprint_um2':sum(area(i) for i in macros),
            'standard_cell_lef_footprint_um2':sum(area(i) for i in insts if not i.getMaster().isBlock()),
            'total_instance_lef_footprint_um2':sum(area(i) for i in insts),
            'area_note':'OpenDB LEF geometry; macro footprint includes whitespace and is not macro logical cell area.',
            'physical_port_geometry_sha256':port_h.hexdigest(),
            'branches_including_physical_ports':{k:dict(v) for k,v in counts.items()},
            'maximum_branch_by_type':maximum,'skipped_nets':dict(skipped)}
    Path(args.report_json).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
