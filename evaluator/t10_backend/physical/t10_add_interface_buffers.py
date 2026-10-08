"""Add positive RVT buffers at the existing complete-DUT interface pins.

Preserve all old instance geometry and every unaffected connection. Prove
each changed input and each output port reconnects through one positive
buffer to its original net. Clock, reset and power ports are excluded.
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from t10_place_top_port_buffers import port_point
from t10_repair_top_clock_channels import NewCellPlacer, xy, distance
from t10_repair_top_data_controls import pin_key, snapshot, reserve_local_row


def main():
    import odb
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('input_odb','output_odb','report_json'): p.add_argument(arg)
    args = p.parse_args(); started = time.monotonic()
    assert not Path(args.output_odb).exists()
    db = odb.dbDatabase.create(); odb.read_db(db,args.input_odb)
    block = db.getChip().getBlock(); dbu = block.getDbUnitsPerMicron()
    originals = list(block.getInsts())
    macros = [i for i in originals if i.getMaster().isBlock()]; assert len(macros)==16
    master = next((lib.findMaster('BUFx12_ASAP7_75t_R') for lib in db.getLibs()
                   if lib.findMaster('BUFx12_ASAP7_75t_R')), None)
    assert master
    ports = sorted((t for t in block.getBTerms() if t.getName() not in ('clk','rst_n')
                    and str(t.getSigType()) == 'SIGNAL'),key=lambda t:t.getName())
    def geometry_hash():
        h=hashlib.sha256()
        for t in sorted(block.getBTerms(),key=lambda t:t.getName()):
            h.update(repr((t.getName(),str(t.getIoType()),str(t.getSigType()),
                           [(b.getTechLayer().getName(),b.xMin(),b.yMin(),b.xMax(),b.yMax())
                            for pin in t.getBPins() for b in pin.getBoxes()])).encode())
        return h.hexdigest()
    io_sha = geometry_hash()
    changed = {pin_key(t) for port in ports if str(port.getIoType())=='INPUT'
               for t in port.getNet().getITerms() if str(t.getIoType())=='INPUT'}
    before = snapshot(originals,changed)
    placer = NewCellPlacer(block,[i for i in originals if not i.getMaster().isBlock()])
    new_names=set(); mutations=[]; reserves=[]; lengths=[]
    for index,port in enumerate(ports):
        kind=str(port.getIoType()); assert kind in ('INPUT','OUTPUT')
        net=port.getNet(); point=port_point(port)
        name=('input' if kind=='INPUT' else 'output')+str(index)
        assert not block.findInst(name) and not block.findNet('t10_interface_'+str(index))
        inst=odb.dbInst.create(block,master,name)
        fresh=odb.dbNet.create(block,'t10_interface_'+str(index)); fresh.setSigType('SIGNAL')
        if kind=='INPUT':
            assert not [t for t in net.getITerms() if str(t.getIoType())=='OUTPUT']
            loads=[t for t in net.getITerms() if str(t.getIoType())=='INPUT']
            for t in loads: t.connect(fresh)
            inst.findITerm('A').connect(net); inst.findITerm('Y').connect(fresh)
            assert inst.findITerm('A').getNet()==port.getNet()
            for t in loads: assert t.getNet()==inst.findITerm('Y').getNet()
            pins=[pin_key(t) for t in loads]
        else:
            inst.findITerm('A').connect(net); inst.findITerm('Y').connect(fresh)
            port.connect(fresh)
            assert port.getNet()==inst.findITerm('Y').getNet()
            assert inst.findITerm('A').getNet()==net
            pins=[]
        for t in inst.getITerms():
            if str(t.getSigType()) in ('POWER','GROUND'):
                supply=block.findNet('VDD' if str(t.getSigType())=='POWER' else 'VSS')
                if supply: t.connect(supply)
        movement=placer.place(inst,point)
        if movement>100*dbu:
            reserves.append(reserve_local_row(block,placer,inst,point,macros,odb))
            movement=placer.place(inst,point)
        assert movement<=100*dbu,(name,movement/dbu)
        pin=inst.findITerm('A' if kind=='INPUT' else 'Y')
        lengths.append(distance(xy(pin),point)/dbu)
        new_names.add(name)
        mutations.append({'port':port.getName(),'direction':kind,'original_net':net.getName(),
                          'buffer':name,'changed_input_pins':pins})
    assert snapshot(originals,changed)==before and geometry_hash()==io_sha
    # Independently retrace after all ports have been transformed. Do not
    # rely only on the assertions made while constructing each buffer.
    for m in mutations:
        inst=block.findInst(m['buffer']); port=block.findBTerm(m['port'])
        assert inst.getMaster()==master
        if m['direction']=='INPUT':
            assert inst.findITerm('A').getNet().getName()==m['original_net']
            assert port.getNet()==inst.findITerm('A').getNet()
            for name,pin in m['changed_input_pins']:
                assert block.findInst(name).findITerm(pin).getNet()==inst.findITerm('Y').getNet()
        else:
            assert inst.findITerm('A').getNet().getName()==m['original_net']
            assert port.getNet()==inst.findITerm('Y').getNet()
    odb.write_db(db,args.output_odb)
    report={'diagnostic_only':True,'physical_qualification_passed':False,
            'mapped_functional_qualification_passed':False,'tile_macros':16,
            'input_odb':args.input_odb,'original_instance_count':len(originals),
            'instance_count':len(block.getInsts()),'inserted_positive_rvt_buffers':len(new_names),
            'buffer_master':master.getName(),'original_geometry_clock_unmodified_connections_sha256':before,
            'independent_positive_interface_equivalence_passed':True,
            'physical_io_geometry_unchanged':True,'physical_io_geometry_sha256':io_sha,
            'maximum_port_buffer_distance_um':max(lengths),'added_reserve_rows':reserves,
            'mutations':mutations,'elapsed_seconds':time.monotonic()-started}
    Path(args.report_json).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='mutations'},indent=2),flush=True)


if __name__=='__main__': main()
