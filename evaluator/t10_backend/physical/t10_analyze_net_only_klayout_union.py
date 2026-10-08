import json,sys,collections
from openroad import Design,Tech
import odb
import klayout.db as kdb
odb_path,analysis_path,fixed_path,out_path=sys.argv[1:5]
T=Tech();D=Design(T);D.readDb(odb_path);block=D.getBlock()
analysis=json.load(open(analysis_path))
fixed=json.load(open(fixed_path))
no_fixed={(r['type'],r['layer'],r['net'],tuple(r['bbox_dbu'])) for r in fixed['records'] if not r['fixed_shape_hits_within_100dbu']}
records=[r for r in analysis['records'] if (r['type'],r['layer'],r['nets'][0],tuple(r['bbox_dbu'])) in no_fixed]
cache={}
def net_region(name,layer):
 key=(name,layer)
 if key in cache:return cache[key]
 net=block.findNet(name);reg=kdb.Region();it=odb.dbWirePathItr();p=odb.dbWirePath();s=odb.dbWirePathShape();it.begin(net.getWire())
 while it.getNextPath(p):
  while it.getNextShape(s):
   o=s.shape
   if o.isVia():
    x,y=o.getViaXY();v=o.getTechVia() or o.getVia()
    for b in v.getBoxes():
     l=b.getTechLayer()
     if l and l.getName()==layer:reg.insert(kdb.Box(b.xMin()+x,b.yMin()+y,b.xMax()+x,b.yMax()+y))
   else:
    l=o.getTechLayer()
    if l and l.getName()==layer:
     b=o.getBox();reg.insert(kdb.Box(b.xMin(),b.yMin(),b.xMax(),b.yMax()))
 reg.merge();cache[key]=reg;return reg
def gap(a,b):
 dx=max(b[0]-a[2],a[0]-b[2],0);dy=max(b[1]-a[3],a[1]-b[3],0);return max(dx,dy)
def bt(b):return (b.left,b.bottom,b.right,b.top)
spacing={'M1':31,'M2':31,'M3':31,'M4':40,'M5':40,'M6':40,'M7':40}
width={'M1':18,'M2':18,'M3':18,'M4':24,'M5':24,'M6':32,'M7':32}
rule_cache={}
out=[]
for r in records:
 name=r['nets'][0];layer=r['layer'];key=(name,layer)
 if key not in rule_cache:
  reg=net_region(name,layer);sp=[bt(e.bbox()) for e in reg.space_check(spacing[layer]).each()];nt=[bt(e.bbox()) for e in reg.notch_check(spacing[layer]).each()];wd=[bt(e.bbox()) for e in reg.width_check(width[layer]).each()]
  rule_cache[key]=(sp,nt,wd,len(reg))
 sp,nt,wd,polys=rule_cache[key];b=r['bbox_dbu']
 near={'space':min([gap(b,x) for x in sp],default=None),'notch':min([gap(b,x) for x in nt],default=None),'width':min([gap(b,x) for x in wd],default=None)}
 out.append({'type':r['type'],'layer':layer,'net':name,'bbox_dbu':b,'merged_polygon_count':polys,'minimum_rules_nm':{'space_or_notch':spacing[layer],'width':width[layer]},'nearest_merged_rule_violation_dbu':near,'merged_rule_violation_within_100dbu':any(v is not None and v<=100 for v in near.values())})
cnt=collections.Counter(x['merged_rule_violation_within_100dbu'] for x in out)
print('records',len(out),'near_rule',dict(cnt),'unique_net_layers',len(rule_cache))
for x in out:
 if x['merged_rule_violation_within_100dbu']:print('NEAR',x)
json.dump({'method':'KLayout 0.30.12 per-net same-layer rectangle/via-enclosure union; conservative minimum space/notch and width checks','records':out},open(out_path,'w'),indent=2);open(out_path,'a').write('\n')

