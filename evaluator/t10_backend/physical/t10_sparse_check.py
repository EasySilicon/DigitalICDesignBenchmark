import argparse,bisect,collections,json,odb,time
p=argparse.ArgumentParser();p.add_argument('odb');p.add_argument('report');args=p.parse_args();t=time.monotonic()
db=odb.dbDatabase.create();odb.read_db(db,args.odb);block=db.getChip().getBlock()
rows=collections.defaultdict(list)
for r in block.getRows():
 x,y=r.getOrigin();rows[y].append((x,x+r.getSpacing()*r.getSiteCount(),r.getSpacing(),str(r.getOrient())))
for y in rows:
 rows[y].sort()
 for a,b in zip(rows[y],rows[y][1:]):
  if a[1]>b[0]:raise RuntimeError(f'overlapping row segments at y={y}: {a} {b}')
macro_boxes=[]
intervals=collections.defaultdict(list);count=0
for inst in block.getInsts():
 status=str(inst.getPlacementStatus());bb=inst.getBBox()
 if status=='LOCKED':
  macro_boxes.append((bb.xMin(),bb.yMin(),bb.xMax(),bb.yMax(),inst.getName()))
 elif status=='PLACED':
  x0,y0,x1,y1=bb.xMin(),bb.yMin(),bb.xMax(),bb.yMax()
  if y1-y0!=270 or y0 not in rows:raise RuntimeError(f'invalid row/height {inst.getName()}')
  segments=rows[y0];starts=[seg[0] for seg in segments];idx=bisect.bisect_right(starts,x0)-1
  if idx<0:raise RuntimeError(f'outside row {inst.getName()}')
  seg=segments[idx]
  if x0<seg[0] or x1>seg[1] or (x0-seg[0])%seg[2]!=0 or str(inst.getOrient())!=seg[3]:
   raise RuntimeError(f'bad placement {inst.getName()} {(x0,y0,x1,y1)} {seg}')
  intervals[y0].append((x0,x1,inst.getName()));count+=1
 else:raise RuntimeError(f'unexpected status {status}: {inst.getName()}')
print('loaded',count,'standard cells',len(macro_boxes),'macros',flush=True)
for y,items in intervals.items():
 items.sort()
 for left,right in zip(items,items[1:]):
  if left[1]>right[0]:raise RuntimeError(f'cell overlap y={y}: {left} {right}')
blocked=collections.defaultdict(list);ys=sorted(rows)
for x0,y0,x1,y1,name in macro_boxes:
 start=bisect.bisect_right(ys,y0-270);end=bisect.bisect_left(ys,y1)
 for y in ys[start:end]:
  if y+270>y0 and y<y1:blocked[y].append((x0,x1,name))
for y in blocked:blocked[y].sort()
for y,items in intervals.items():
 b=blocked[y];starts=[v[0] for v in b]
 for x0,x1,name in items:
  idx=bisect.bisect_left(starts,x1)
  if idx and b[idx-1][1]>x0:raise RuntimeError(f'macro overlap {name} {b[idx-1]}')
report={'standard_cells':count,'macros':len(macro_boxes),'physical_rows':len(rows),'row_segments':sum(len(v) for v in rows.values()),'cell_overlap_count':0,'macro_overlap_count':0,'site_or_orientation_errors':0,'elapsed_seconds':time.monotonic()-t}
with open(args.report,'w') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report),flush=True)
