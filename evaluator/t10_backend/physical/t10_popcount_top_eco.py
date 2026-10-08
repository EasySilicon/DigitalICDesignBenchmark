"""Diagnostic one-pin mapped ECO for the already qualified pop-count RTL.

Replace final_pop's output-valid reduction input with the existing nonempty
queue decoder. Preserve all geometry, clocks, cells and other connections.
This is a timing experiment; release still requires complete qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
from t10_paths import scratch_root


def snapshot(block, excluded_pin):
    h = hashlib.sha256()
    for inst in sorted(block.getInsts(), key=lambda i:i.getName()):
        h.update(repr((inst.getName(),inst.getMaster().getName(),inst.getLocation(),
                       str(inst.getOrient()),str(inst.getPlacementStatus()))).encode())
        for pin in sorted(inst.getITerms(),key=lambda p:p.getMTerm().getName()):
            if (inst.getName(),pin.getMTerm().getName()) == excluded_pin:
                continue
            net=pin.getNet()
            h.update(repr((pin.getMTerm().getName(),net.getName() if net else None)).encode())
    return h.hexdigest()


def main():
    import odb
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_odb")
    p.add_argument("output_odb")
    p.add_argument("report_json")
    p.add_argument("--qualification-root", type=Path,
                   default=Path(os.environ.get("T10_POPCOUNT_QUALIFICATION_ROOT",
                                              str(scratch_root() / 't10_qualification/v65_popcount'))))
    args=p.parse_args()
    qualification=args.qualification_root.expanduser().resolve()
    qbytes=(qualification/'qualification.json').read_bytes()
    assert hashlib.sha256(qbytes).hexdigest()=='c56b3c71801207bb17c925cc6abbb846db2dd3c06b807494d2d83070f02889a8'
    q=json.loads(qbytes)
    assert q['qualification_passed'] and q['cases']==2752 and q['structure']['pe_instances']==256
    assert q['reset_probe_passed'] and not q['failures']
    candidate=(qualification/'rtl/npu_systolic_matmul_16x16.sv').read_bytes()
    assert hashlib.sha256(candidate).hexdigest()==q['rtl_sha256']=='68da56e51120c4dd6b34cfd7100409c47b13d661cb97845acd8a2566c2805531'
    db=odb.dbDatabase.create()
    odb.read_db(db,args.input_odb)
    block=db.getChip().getBlock()
    gate=block.findInst('_05961_')
    reduction=block.findInst('_05960_')
    decode=block.findInst('_06006_')
    count_buf=block.findInst('_05895_')
    for inst,expected in ((gate,'AND2x2_ASAP7_75t_R'),(reduction,'OR4x1_ASAP7_75t_R'),
                          (decode,'NAND2x1_ASAP7_75t_R'),(count_buf,'BUFx2_ASAP7_75t_R')):
        assert inst and inst.getMaster().getName()==expected
    counts={}
    for inst in block.getInsts():
        name=inst.getName().replace('\\','')
        for bit in (0,1):
            if name==f'output_queue_count[{bit}]$_DFFE_PN0P_':
                assert inst.getMaster().getName()=='DFFASRHQNx1_ASAP7_75t_R'
                assert bit not in counts
                counts[bit]=inst
    assert len(counts)==2
    assert count_buf.findITerm('A').getNet()==counts[0].findITerm('QN').getNet()
    assert decode.findITerm('A').getNet()==counts[1].findITerm('QN').getNet()
    assert decode.findITerm('B').getNet()==count_buf.findITerm('Y').getNet()
    changed_pin=gate.findITerm('B')
    assert changed_pin.getNet()==reduction.findITerm('Y').getNet()
    old_net=changed_pin.getNet().getName()
    new_net=decode.findITerm('Y').getNet()
    if old_net==new_net.getName():
        raise RuntimeError('Pop-count ECO already present')
    excluded=(gate.getName(),'B')
    before=snapshot(block,excluded)
    changed_pin.connect(new_net)
    after=snapshot(block,excluded)
    assert before==after
    assert len([i for i in block.getInsts() if i.getMaster().isBlock()])==16
    output=Path(args.output_odb)
    output.parent.mkdir(parents=True,exist_ok=True)
    odb.write_db(db,str(output))
    report={'diagnostic_only':True,'mapped_functional_qualification_passed':False,
            'status':'one_pin_popcount_ECO_pending_mapped_function_and_physical_qualification',
            'candidate_rtl_sha256':q['rtl_sha256'],'candidate_functional_cases':2752,
            'candidate_qualification_sha256':hashlib.sha256(qbytes).hexdigest(),
            'input_odb':args.input_odb,'instance_count':len(block.getInsts()),
            'tile_macros':16,'pe_count_by_hierarchy':256,
            'changed_pin':gate.getName()+'/B','old_net':old_net,'new_net':new_net.getName(),
            'decoder_master':decode.getMaster().getName(),
            'decoder_equation':'NAND(count_bit_1_QN, BUF(count_bit_0_QN)) = count != 0',
            'all_geometry_clocks_and_other_connections_sha256':before,
            'all_geometry_clocks_and_other_connections_unchanged':True,
            'frozen_reference_RTL_changed':False}
    Path(args.report_json).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
