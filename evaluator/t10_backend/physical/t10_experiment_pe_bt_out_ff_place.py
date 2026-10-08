import odb,re,sys
D=odb.dbDatabase.create();odb.read_db(D,sys.argv[1]);b=D.getChip().getBlock();d=b.getDbUnitsPerMicron()
pat=re.compile(r'bt_out_payload\\\[(\d+)\\\]\$_DFF_PN0_')
targets={}
for inst in b.getInsts():
 m=pat.fullmatch(inst.getName())
 if m: targets[int(m.group(1))]=inst
assert sorted(targets)==list(range(27)),sorted(targets)
rows=sorted((r for r in b.getRows() if 19*d < r.getOrigin()[1] < 28*d and r.getOrigin()[0] < 130*d < r.getOrigin()[0]+r.getSpacing()*r.getSiteCount()),key=lambda r:r.getOrigin()[1])
assert len(rows)>=27,len(rows)
for bit,inst in targets.items():
 row=rows[bit];ox,y=row.getOrigin();pitch=row.getSpacing();x=ox+round((130*d-ox)/pitch)*pitch
 inst.setOrient(str(row.getOrient()));inst.setLocation(x,y);inst.setPlacementStatus('FIRM')
 print(bit,inst.getName(),x/d,y/d)
odb.write_db(D,sys.argv[2])
