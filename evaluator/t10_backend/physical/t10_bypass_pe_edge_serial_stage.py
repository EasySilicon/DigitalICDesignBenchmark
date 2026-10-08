import odb,sys,json
src,dst,report=sys.argv[1:4]
db=odb.dbDatabase.create(); odb.read_db(db,src); b=db.getChip().getBlock()
names=['clkbuf_1_0_0_clk_edge_parallel','clkbuf_1_1_0_clk_edge_parallel']
audit=[]
for name in names:
 inst=b.findInst(name)
 if inst is None: raise RuntimeError(f'missing {name}')
 ins=[t for t in inst.getITerms() if str(t.getIoType())=='INPUT' and t.getMTerm().getName() not in ('VDD','VSS')]
 outs=[t for t in inst.getITerms() if str(t.getIoType())=='OUTPUT']
 if len(ins)!=1 or len(outs)!=1: raise RuntimeError(f'bad pins {name}')
 inet=ins[0].getNet(); onet=outs[0].getNet()
 loads=[t for t in onet.getITerms() if str(t.getIoType())=='INPUT']
 if len(loads)!=1 or not loads[0].getInst().getMaster().getName().startswith('BUF'):
  raise RuntimeError(f'unsafe loads {name}: {len(loads)}')
 load=loads[0]; rec={'removed':name,'master':inst.getMaster().getName(),'input_net':inet.getName(),'output_net':onet.getName(),'only_load':load.getInst().getName()+'/'+load.getMTerm().getName()}
 load.disconnect(); load.connect(inet); odb.dbInst_destroy(inst)
 if list(onet.getITerms()) or list(onet.getBTerms()): raise RuntimeError(f'net not empty {onet.getName()}')
 odb.dbNet_destroy(onet); audit.append(rec)
odb.write_db(db,dst)
with open(report,'w') as f: json.dump({'bypasses':audit},f,indent=2)
print('T10_EDGE_SERIAL_BYPASS',audit)
