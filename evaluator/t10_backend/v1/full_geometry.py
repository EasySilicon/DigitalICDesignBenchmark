"""Complete OpenDB geometry: path shapes plus explicit RECT patch metal.

The pinned SWIG binding hides dbWireShapeItr. dbWirePathItr intentionally
skips RECT; supplement it using the public decoder and raw RECT operands.
"""
from pathlib import Path
import sys

import odb

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'physical'))
from t10_manual_v15_inspect import wire_shapes as path_shapes

POLICY='OpenDB_paths_plus_explicit_RECT_decoder'


def wire_shapes(net):
    yield from path_shapes(net)
    wire=net.getWire()
    if wire is None:
        return
    decoder=odb.dbWireDecoder(); decoder.begin(wire)
    while True:
        opcode=decoder.next()
        if opcode==odb.dbWireDecoder.END_DECODE:
            break
        if opcode!=odb.dbWireDecoder.RECT:
            continue
        index=decoder.getJunctionId()
        raw=wire.getOpcode(index)
        raw=raw if isinstance(raw,int) else ord(raw)
        if raw&31!=14 or index+3>=wire.length():
            raise ValueError('unexpected RECT wire encoding')
        x,y=wire.getCoord(index)
        dx0,dy0,dx1,dy1=[wire.getData(index+i) for i in range(4)]
        yield dict(kind='route_patch',net=net.getName(),layer=decoder.getLayer().getName(),
                   bbox=(x+dx0,y+dy0,x+dx1,y+dy1),wire_index=index)
