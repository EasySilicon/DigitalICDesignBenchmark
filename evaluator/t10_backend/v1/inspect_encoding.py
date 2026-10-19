"""Read-only raw path boundaries for exact, reviewed route edits."""
import sys
import odb

db=odb.dbDatabase.create(); odb.read_db(db,sys.argv[1]); block=db.getChip().getBlock()
for name in sys.argv[2:]:
    net=block.findNet(name)
    if not net or not net.getWire():
        raise ValueError('missing net: '+name)
    wire=net.getWire(); print('NET',name,'length',wire.length())
    ops=[wire.getOpcode(i) for i in range(wire.length())]
    ops=[op if isinstance(op,int) else ord(op) for op in ops]
    starts=[i for i,op in enumerate(ops) if op&31==0]+[wire.length()]
    for a,b in zip(starts,starts[1:]):
        print('PATH',a,b,[(i,ops[i],wire.getData(i)) for i in range(a,b)])
