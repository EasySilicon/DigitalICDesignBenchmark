"""Measure long cell-driven data branches of the complete physical T10 top."""
import argparse
import json
from collections import Counter
from pathlib import Path

from t10_repair_top_clock_channels import distance, xy


def main():
    import odb
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input_odb')
    p.add_argument('output_json')
    p.add_argument('--threshold-um',type=float,default=300)
    args=p.parse_args()
    db=odb.dbDatabase.create();odb.read_db(db,args.input_odb)
    block=db.getChip().getBlock();dbu=block.getDbUnitsPerMicron()
    assert len([i for i in block.getInsts() if i.getMaster().isBlock()])==16
    branches=[];skipped=Counter()
    for net in block.getNets():
        if str(net.getSigType())!='SIGNAL':continue
        drivers=[t for t in net.getITerms() if str(t.getIoType())=='OUTPUT']
        if len(drivers)!=1:skipped['not_one_cell_driver']+=1;continue
        loads=[t for t in net.getITerms() if str(t.getIoType())=='INPUT']
        if any(t.getMTerm().getName() in ('RESETN','SETN','rst_n','RN','SN','RESET','SET') for t in loads):
            skipped['async_reset_or_constant_control']+=1;continue
        root=drivers[0];point=xy(root)
        for pin in loads:
            length=distance(point,xy(pin))/dbu
            if length>args.threshold_um:
                branches.append({'net':net.getName(),'driver':root.getInst().getName(),
                                 'driver_pin':root.getMTerm().getName(),
                                 'driver_master':root.getInst().getMaster().getName(),
                                 'sink':pin.getInst().getName(),'sink_pin':pin.getMTerm().getName(),
                                 'sink_master':pin.getInst().getMaster().getName(),
                                 'driver_xy_um':[a/dbu for a in point],
                                 'sink_xy_um':[a/dbu for a in xy(pin)],
                                 'manhattan_um':length,'fanout':len(loads)})
    branches.sort(key=lambda v:(-v['manhattan_um'],v['net'],v['sink']))
    report={'diagnostic_only':True,'input_odb':args.input_odb,'tile_macros':16,
            'instance_count':len(block.getInsts()),'threshold_um':args.threshold_um,
            'long_branches':len(branches),'long_nets':len({b['net'] for b in branches}),
            'estimated_unshared_buffers_at_200um':sum(int(b['manhattan_um']/200) for b in branches),
            'long_branches_by_threshold_um':{str(t):sum(b['manhattan_um']>t for b in branches) for t in (300,500,1000,2000)},
            'skipped_nets':dict(skipped),'branches':branches}
    Path(args.output_json).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='branches'}))
    for b in branches[:8]:print(json.dumps(b))


if __name__=='__main__':main()
