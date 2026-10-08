import odb,sys,json
src,dst,report=sys.argv[1:4]
db=odb.dbDatabase.create(); odb.read_db(db,src); b=db.getChip().getBlock(); raw=b.findNet('clk')
roots=[b.findInst('clk_core_parallel_root'),b.findInst('clk_edge_parallel_root')]
if any(x is None for x in roots): raise RuntimeError('parallel roots absent')
def pin(inst,name):
    return next(t for t in inst.getITerms() if t.getMTerm().getName()==name)
paths={}; doomed=set(); candidate_nets=set()
for root in roots:
    cur=pin(root,'A').getNet(); path=[]
    while cur != raw:
        drivers=[t for t in cur.getITerms() if str(t.getIoType())=='OUTPUT']
        if len(drivers)!=1: raise RuntimeError(f'{cur.getName()} driver count {len(drivers)}')
        inst=drivers[0].getInst(); master=inst.getMaster().getName()
        if not master.startswith(('BUF','INV')): raise RuntimeError(f'nonbuffer {inst.getName()} {master}')
        path.append(inst.getName()); doomed.add(inst); candidate_nets.add(cur)
        ins=[t for t in inst.getITerms() if str(t.getIoType())=='INPUT' and t.getMTerm().getName() not in ('VDD','VSS')]
        if len(ins)!=1 or ins[0].getNet() is None: raise RuntimeError(f'bad input {inst.getName()}')
        cur=ins[0].getNet()
    paths[root.getName()]=path
for root in roots:
    t=pin(root,'A'); t.disconnect(); t.connect(raw)
doomed_names=sorted(inst.getName() for inst in doomed)
for inst in doomed:
    for t in list(inst.getITerms()):
        if t.getNet() is not None: candidate_nets.add(t.getNet())
    odb.dbInst_destroy(inst)
destroyed_nets=[]
for net in candidate_nets:
    if net==raw: continue
    if not list(net.getITerms()) and not list(net.getBTerms()):
        destroyed_nets.append(net.getName()); odb.dbNet_destroy(net)
loads=sorted(t.getInst().getName() for t in raw.getITerms())
if loads!=sorted(x.getName() for x in roots): raise RuntimeError(f'raw loads {loads}')
odb.write_db(db,dst)
with open(report,'w') as f: json.dump({'paths':paths,'destroyed_instances':doomed_names,'destroyed_nets':sorted(destroyed_nets),'raw_loads':loads},f,indent=2)
print('T10_CLOCK_PRESTAGE_BYPASS',paths,'raw_loads',loads)
