import json,sys,collections
from openroad import Design,Tech
import odb
odb_path,analysis_path,out_path=sys.argv[1:4]
T=Tech();D=Design(T);D.readDb(odb_path);block=D.getBlock()
records=[r for r in json.load(open(analysis_path))['records'] if r['source_class']=='net_only' and r['type']!='Min Width']
inst_cache={}
def tx_rect(tr,b):
 p1=odb.Point(b.xMin(),b.yMin());p2=odb.Point(b.xMax(),b.yMax());tr.apply(p1);tr.apply(p2)
 return (min(p1.x(),p2.x()),min(p1.y(),p2.y()),max(p1.x(),p2.x()),max(p1.y(),p2.y()))
def inst_shapes(name):
 if name in inst_cache:return inst_cache[name]
 inst=block.findInst(name)
 if inst is None:return []
 tr=inst.getTransform(); out=[]
 for b in inst.getMaster().getObstructions():
  l=b.getTechLayer()
  if l:out.append({'kind':'obstruction','layer':l.getName(),'bbox':tx_rect(tr,b),'terminal':None,'net':None})
 net_by_mterm={it.getMTerm().getName():(it.getNet().getName() if it.getNet() else None) for it in inst.getITerms()}
 for mt in inst.getMaster().getMTerms():
  for mp in mt.getMPins():
   for b in mp.getGeometry():
    l=b.getTechLayer()
    if l:out.append({'kind':'pin','layer':l.getName(),'bbox':tx_rect(tr,b),'terminal':mt.getName(),'net':net_by_mterm.get(mt.getName())})
 inst_cache[name]=out;return out
bterm_cache={}
def bterm_shapes(netname):
 if netname in bterm_cache:return bterm_cache[netname]
 bt=block.findBTerm(netname);out=[]
 if bt:
  for bp in bt.getBPins():
   for b in bp.getBoxes():
    l=b.getTechLayer()
    if l:out.append({'kind':'bterm_pin','layer':l.getName(),'bbox':(b.xMin(),b.yMin(),b.xMax(),b.yMax()),'terminal':bt.getName(),'net':bt.getNet().getName() if bt.getNet() else None})
 bterm_cache[netname]=out;return out
def gap(a,b):
 dx=max(b[0]-a[2],a[0]-b[2],0);dy=max(b[1]-a[3],a[1]-b[3],0)
 return max(dx,dy)
out=[]
for r in records:
 net=r['nets'][0];hits=[]
 names={x['name'] for x in r.get('near_1um_instances',[])}
 for name in names:
  for s in inst_shapes(name):
   if s['layer']==r['layer'] and gap(r['bbox_dbu'],s['bbox'])<=100:
    h=dict(s);h['instance']=name;h['gap_dbu']=gap(r['bbox_dbu'],s['bbox']);hits.append(h)
 for s in bterm_shapes(net):
  if s['layer']==r['layer'] and gap(r['bbox_dbu'],s['bbox'])<=100:
   h=dict(s);h['gap_dbu']=gap(r['bbox_dbu'],s['bbox']);hits.append(h)
 out.append({'type':r['type'],'layer':r['layer'],'net':net,'bbox_dbu':r['bbox_dbu'],'fixed_shape_hits_within_100dbu':hits})
cnt=collections.Counter()
for r in out:
 hs=r['fixed_shape_hits_within_100dbu']
 if not hs:cnt['no_fixed_shape']+=1
 elif all(h['kind'] in ('pin','bterm_pin') and h['net']==r['net'] for h in hs):cnt['same_net_pin_only']+=1
 else:
  cnt['obstruction_or_other_pin']+=1
print('records',len(out),dict(cnt))
for r in out:
 hs=r['fixed_shape_hits_within_100dbu']
 if hs and not all(h['kind'] in ('pin','bterm_pin') and h['net']==r['net'] for h in hs):
  print('ACTIONABLE',r)
json.dump({'method':'master obstruction and terminal geometry transformed to block coordinates; 100 DBU marker halo','summary':dict(cnt),'records':out},open(out_path,'w'),indent=2);open(out_path,'a').write('\n')

