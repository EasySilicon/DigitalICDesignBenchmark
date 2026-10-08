"""Read-only audit of full-DUT input packing, physical locality and v93 path.

Report native DB units and actual I/O, macro and register pin coordinates.
Distances are Manhattan geometry, not extracted delays or timing passes.
"""
import argparse
import json
import re
import statistics
from pathlib import Path

from t10_place_top_port_buffers import port_point
from t10_repair_top_clock_channels import xy, distance


def main():
    import odb
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input_odb'); p.add_argument('report_json'); args=p.parse_args()
    db=odb.dbDatabase.create(); odb.read_db(db,args.input_odb)
    block=db.getChip().getBlock(); dbu=block.getDbUnitsPerMicron()
    insts=list(block.getInsts()); macros=[i for i in insts if i.getMaster().isBlock()]
    assert len(macros)==16
    normalized={i.getName().replace('\\',''):i for i in insts}
    tiles={}
    for inst in macros:
        m=re.search(r'tile_row\[(\d)\]\.tile_col\[(\d)\]\.tile$',inst.getName().replace('\\',''))
        assert m; tiles[tuple(map(int,m.groups()))]=inst
    ingress={}; controls={}
    for name,inst in normalized.items():
        if not inst.getMaster().getName().startswith(('DFF','SDFF')): continue
        m=re.match(r'ingress_([ab])_data\[(\d+)\]',name)
        if m: ingress[m[1],int(m[2])]=inst
        m=re.match(r'([ab])_ctrl_payload\[(\d+)\]\[(\d+)\]',name)
        if m: controls[m[1],int(m[2]),int(m[3])]=inst
    def um(point):return [v/dbu for v in point]
    def summary(values):
        return {'minimum_um':min(values),'median_um':statistics.median(values),'maximum_um':max(values),
                'above_1000_um':sum(v>1000 for v in values)}
    inputs=[]; missing=[]
    for axis in ('a','b'):
        for lane in range(16):
            ports=[]; qpoints=[]; targets=[]; ingress_distances=[]; port_to_tile=[]; sampled=[]
            tile=tiles[lane//4,0] if axis=='a' else tiles[0,lane//4]
            for bit in range(64):
                index=lane*64+bit
                port=block.findBTerm(f'{axis}_data[{index}]')
                target=tile.findITerm(f'{axis}_in_data[{(lane%4)*64+bit}]')
                assert port and target
                point=port_point(port); end=xy(target)
                ports.append(point); targets.append(end); port_to_tile.append(distance(point,end)/dbu)
                ff=ingress.get((axis,index))
                if not ff:
                    missing.append([axis,index]); continue
                d=ff.findITerm('D'); assert d
                qpoint=xy(d); qpoints.append(qpoint)
                ingress_distances.append(distance(point,qpoint)/dbu)
                if bit in (0,31,63): sampled.append({'bit':index,'port_um':um(point),
                    'ingress_D_um':um(qpoint),'tile_input_um':um(end),'register':ff.getName()})
            row={'axis':axis,'lane':lane,'tile':tile.getName(),'physical_port_box_um':[
                min(q[0] for q in ports)/dbu,min(q[1] for q in ports)/dbu,
                max(q[0] for q in ports)/dbu,max(q[1] for q in ports)/dbu],
                'external_pin_to_ingress_register':summary(ingress_distances),
                'external_pin_to_tile_input_geometric_only':summary(port_to_tile),'samples':sampled}
            if qpoints:row['ingress_register_box_um']=[min(q[0] for q in qpoints)/dbu,min(q[1] for q in qpoints)/dbu,
                max(q[0] for q in qpoints)/dbu,max(q[1] for q in qpoints)/dbu]
            ctrl=[]
            for bit in range(11):
                ff=controls.get((axis,lane,bit))
                if not ff:continue
                term=tile.findITerm(f'{axis}_in_token[{(lane%4)*28+16+bit}]'); assert term
                ctrl.append(distance(xy(ff.findITerm('QN') or ff.findITerm('Q')),xy(term))/dbu)
            if ctrl:row['control_register_to_corresponding_tile_token_pin']=summary(ctrl)
            inputs.append(row)
    assert not missing,missing
    # Exact source/output bit used by the v93 worst setup report.
    driver=tiles[0,1].findITerm('read_data[198]'); assert driver
    sinks=[]
    for t in driver.getNet().getITerms():
        if str(t.getIoType())=='INPUT':sinks.append({'instance':t.getInst().getName(),
            'pin':t.getMTerm().getName(),'xy_um':um(xy(t)),
            'manhattan_um':distance(xy(driver),xy(t))/dbu})
    dest_name='gather_slot[3].gather_group[0].gather_cell[7].gather_lane/gather_data[6]$_DFFE_PP_'
    dest=normalized.get(dest_name)
    sample=controls.get(('b',1,10))
    payload={'input_odb':args.input_odb,'diagnostic_only':True,'db_units_per_micron':dbu,
        'die_um':[v/dbu for v in (block.getDieArea().xMin(),block.getDieArea().yMin(),
                                  block.getDieArea().xMax(),block.getDieArea().yMax())],
        'tile_macros':16,'standard_cells':len(insts)-16,
        'macro_geometry':[{'name':i.getName(),'origin_um':um(i.getLocation()),
            'master_width_um':i.getMaster().getWidth()/dbu,'master_height_um':i.getMaster().getHeight()/dbu,
            'orientation':str(i.getOrient())} for i in sorted(macros,key=lambda i:i.getName())],
        'inputs':inputs,'missing_ingress_registers':missing,
        'v93_critical_source':{'tile':'tile_row[0].tile_col[1].tile','pin':'read_data[198]',
            'logical_C_row':0,'logical_C_column':7,'result_bit':6,'source_um':um(xy(driver)),
            'fanout':len(sinks),'loads':sinks,
            'gather_register_D_um':um(xy(dest.findITerm('D'))) if dest else None},
        'b_control_lane1_bit10_register':{'name':sample.getName(),
            'Q_um':um(xy(sample.findITerm('QN') or sample.findITerm('Q')))} if sample else None}
    Path(args.report_json).write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps({k:v for k,v in payload.items() if k not in ('inputs','macro_geometry')},indent=2),flush=True)


if __name__=='__main__':main()
