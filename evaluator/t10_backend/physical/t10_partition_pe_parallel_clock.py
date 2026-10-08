import odb,sys
src,dst=sys.argv[1:3]
db=odb.dbDatabase.create(); odb.read_db(db,src); b=db.getChip().getBlock(); raw=b.findNet('clk')
master=None
for lib in db.getLibs():
    m=lib.findMaster('BUFx24_ASAP7_75t_R')
    if m is not None: master=m; break
if master is None: raise RuntimeError('BUFx24 absent')
core=odb.dbNet_create(b,'clk_core_parallel'); edge=odb.dbNet_create(b,'clk_edge_parallel')
roots=[]
for name,net in [('clk_core_parallel_root',core),('clk_edge_parallel_root',edge)]:
    inst=odb.dbInst_create(b,master,name); pins={t.getMTerm().getName():t for t in inst.getITerms()}
    pins['A'].connect(raw); pins['Y'].connect(net)
    for p,n in [('VDD','VDD'),('VSS','VSS')]:
        q=b.findNet(n)
        if q is not None and p in pins: pins[p].connect(q)
    roots.append(inst)
boxes=[box for pin in b.findBTerm('clk').getBPins() for box in pin.getBoxes()]
box=boxes[0]; px=(box.xMin()+box.xMax())//2; py=(box.yMin()+box.yMax())//2
rows=sorted(b.getRows(),key=lambda r:abs(r.getOrigin()[1]-py)); row=rows[0]
x0,y0=row.getOrigin(); pitch=row.getSpacing(); xmax=x0+pitch*row.getSiteCount()
base=max(x0,min(xmax-2*master.getWidth(),x0+round((px-x0)/pitch)*pitch))
for i,inst in enumerate(roots):
    inst.setLocation(base+i*master.getWidth(),y0); inst.setOrient(str(row.getOrient())); inst.setPlacementStatus('PLACED')
boundary=('a_out','b_out','at_out','bt_out','result')
edge_n=core_n=0
for term in list(raw.getITerms()):
    if term.getInst() in roots: continue
    if str(term.getMTerm().getSigType())!='CLOCK': continue
    name=term.getInst().getName(); term.disconnect()
    if name.startswith(boundary): term.connect(edge); edge_n+=1
    else: term.connect(core); core_n+=1
print('T10_CLOCK_PARALLEL edge',edge_n,'core',core_n,'root_xy',base,y0)
if edge_n!=253 or core_n!=11130: raise RuntimeError(f'unexpected edge={edge_n} core={core_n}')
odb.write_db(db,dst)
