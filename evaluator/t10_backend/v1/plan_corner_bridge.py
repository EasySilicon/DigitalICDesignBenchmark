"""Read-only bounded clearance study; output is NOT native DRC qualification.

Suggest fixed M2-M7 segments for the reviewed seed29 net471 cut. No router,
rip-up, placement change, database write, or automatic physical ECO is performed.
Every proposed segment still needs review and native checks after application.
"""
import argparse
from collections import defaultdict
from functools import lru_cache
import heapq
import json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('geometry')
    parser.add_argument('output')
    parser.add_argument('--net',default=r'quad_sum\[3\]\[471\]')
    parser.add_argument('--source',action='append',help='layer,xmin,y,xmax on a surviving horizontal wire')
    parser.add_argument('--sink',action='append',help='layer,xmin,y,xmax on a surviving horizontal wire')
    parser.add_argument('--conservative-eol',action='store_true',help='also reserve aligned line-end gaps before native checks')
    parser.add_argument('--check-plan',help='validate fixed coordinates against this current geometry instead of suggesting a path')
    args=parser.parse_args()
    data=json.load(open(args.geometry))
    if data.get('special_routes_included') is not True:
        raise ValueError('supply special-route geometry is mandatory')
    target=args.net
    if not any(s.get('net')==target for s in data['shapes']):
        raise ValueError('exact target net absent')
    x0,y0,x1,y1=data['region']
    # Work away from the inspection boundary; unseen geometry cannot be used.
    x0+=80;y0+=80;x1-=80;y1-=80
    tracks={layer:set(range(((x0-phase+pitch-1)//pitch)*pitch+phase,x1+1,pitch))
            for layer,pitch,phase in ((3,36,9),(5,48,12),(7,64,16))}
    xs=sorted(set.union(*tracks.values()))
    m2ys={round((s['bbox'][1]+s['bbox'][3])/2) for s in data['shapes']
          if s['kind']=='route_segment' and s['layer']=='M2' and
          s['bbox'][2]-s['bbox'][0]>s['bbox'][3]-s['bbox'][1]}
    m2ys={y for y in m2ys if y0<=y<=y1};m2ys.add(284895)
    m4ys=set(range(((y0-12+47)//48)*48+12,y1+1,48))
    m6ys=set(range(((y0-16+63)//64)*64+16,y1+1,64))
    rows={2:m2ys,4:m4ys,6:m6ys}
    sources=[tuple(map(int,s.split(','))) for s in (args.source or ['2,361089,284895,362241','4,363801,284412,364896'])]
    sinks=[tuple(map(int,s.split(','))) for s in (args.sink or ['4,365409,285084,370800'])]
    for layer,lo,y,hi in sources+sinks:
        if layer not in rows or lo>hi or not y0<=y<=y1:
            raise ValueError('invalid surviving-wire attachment')
        rows[layer].add(y)
    ys=sorted(m2ys|m4ys|m6ys); yi={y:i for i,y in enumerate(ys)}
    shapes={};bins=defaultdict(set)
    for s in data['shapes']:
        layer=s['layer'];b=s['bbox']
        if s.get('net')==target or layer not in ('M2','M3','M4','M5','M6','M7','V2','V3','V4','V5','V6'):
            continue
        key=(layer,*b)
        if key in shapes:continue
        shapes[key]=b
        for bx in range(max(x0-100,b[0])//100,min(x1+100,b[2])//100+1):
            for by in range(max(y0-100,b[1])//100,min(y1+100,b[3])//100+1):
                bins[layer,bx,by].add(key)

    @lru_cache(None)
    def free(layer,b,clear):
        nearby=set()
        radius=max(clear,72) if layer.startswith('M') else clear
        for bx in range((b[0]-radius)//100,(b[2]+radius)//100+1):
            for by in range((b[1]-radius)//100,(b[3]+radius)//100+1):
                nearby.update(bins[layer,bx,by])
        for k in nearby:
            a=shapes[k];required=clear
            if layer in ('M4','M5','M6','M7'):
                nominal=24 if layer in ('M4','M5') else 32
                if min(a[2]-a[0],a[3]-a[1])>nominal:required=max(required,72)
            if args.conservative_eol and layer.startswith('M'):
                level=int(layer[1]);nominal=18 if level<=3 else 24 if level<=5 else 32
                aligned=(a[0]<=b[2] and b[0]<=a[2]) if level%2 else (a[1]<=b[3] and b[1]<=a[3])
                if aligned and min(a[2]-a[0],a[3]-a[1])<=nominal:
                    required=max(required,31 if level<=3 else 40 if level in (4,6) else 48 if level==5 else 50)
            if max(a[0]-b[2],b[0]-a[2],a[1]-b[3],b[1]-a[3])<required:return False
        return True

    @lru_cache(None)
    def segment(layer,i,j,k,l):
        width=9 if layer<=3 else 12 if layer<=5 else 16
        a,b,c,d=xs[i],ys[j],xs[k],ys[l]
        return free('M'+str(layer),(min(a,c)-width,min(b,d)-width,
                                    max(a,c)+width,max(b,d)+width),18 if layer<=3 else 24 if layer<=5 else 32)

    @lru_cache(None)
    def via(layer,i,j):
        x,y=xs[i],ys[j]
        if layer==2:
            boxes=(('M2',(-14,-9,14,9),18),('M3',(-9,-14,9,14),18),('V2',(-9,-9,9,9),18))
        elif layer==3:
            boxes=(('M3',(-9,-17,9,17),18),('M4',(-20,-12,20,12),24),('V3',(-9,-12,9,12),34))
        elif layer==4:
            boxes=(('M4',(-23,-12,23,12),24),('M5',(-12,-23,12,23),24),('V4',(-12,-12,12,12),34))
        elif layer==5:
            boxes=(('M5',(-12,-27,12,27),24),('M6',(-23,-16,23,16),32),('V5',(-12,-16,12,16),34))
        else:
            boxes=(('M6',(-27,-16,27,16),32),('M7',(-16,-27,16,27),32),('V6',(-16,-16,16,16),34))
        return all(free(l,(x+a,y+b,x+c,y+d),clear) for l,(a,b,c,d),clear in boxes)

    if args.check_plan:
        proposal=json.load(open(args.check_plan));failures=[]
        if proposal['target']!=target:raise ValueError('plan target mismatch')
        for s in proposal['segments']:
            layer=int(s['layer'][1]);a,b=s['start'],s['end']
            w=9 if layer<=3 else 12 if layer<=5 else 16
            bounds=(min(a[0],b[0])-w,min(a[1],b[1])-w,max(a[0],b[0])+w,max(a[1],b[1])+w)
            if not free(s['layer'],bounds,18 if layer<=3 else 24 if layer<=5 else 32):failures.append(s)
        for v in proposal['vias']:
            if v['x'] not in xs or v['y'] not in yi or not via(int(v['name'][3]),xs.index(v['x']),yi[v['y']]):failures.append(v)
        if failures:raise ValueError('fixed plan conflicts with current geometry: '+json.dumps(failures))
        proposal.update(geometry=args.geometry,checked_plan=args.check_plan,
                        status='current_geometry_clearance_checked_not_DRC_qualified')
        with open(args.output,'x') as out:json.dump(proposal,out,indent=2);out.write('\n')
        print('FIXED PLAN CLEAR:',len(proposal['segments']),'segments,',len(proposal['vias']),'vias; native checks still mandatory')
        return

    dist={};prev={};heap=[]
    for i,x in enumerate(xs):
        for layer,lo,y,hi in sources:
            j=yi[y]
            if lo<=x<=hi and segment(layer,i,j,i,j):
                state=(layer,i,j);dist[state]=0;prev[state]=None;heapq.heappush(heap,(0,state))
    end=None;popped=0
    while heap:
        score,state=heapq.heappop(heap)
        if score!=dist[state]:continue
        layer,i,j=state;popped+=1;x,y=xs[i],ys[j]
        if any(layer==la and yy==y and lo<=x<=hi for la,lo,yy,hi in sinks):
            end=state;break
        neighbors=[]
        if layer%2:
            for nj in (j-1,j+1):
                if 0<=nj<len(ys) and segment(layer,i,j,i,nj):
                    neighbors.append(((layer,i,nj),abs(ys[nj]-y)))
        else:
            for ni in (i-1,i+1):
                if 0<=ni<len(xs) and segment(layer,i,j,ni,j):
                    neighbors.append(((layer,ni,j),abs(xs[ni]-x)))
        for nl in (layer-1,layer+1):
            if not 2<=nl<=7:continue
            vertical=layer if layer%2 else nl
            horizontal=nl if layer%2 else layer
            if x in tracks[vertical] and y in rows[horizontal] and via(min(layer,nl),i,j):
                neighbors.append(((nl,i,j),500))
        for new,cost in neighbors:
            value=score+cost
            if value<dist.get(new,float('inf')):
                dist[new]=value;prev[new]=state;heapq.heappush(heap,(value,new))
    if end is None:raise ValueError(f'no bounded clearance path in {popped} reachable states')
    path=[];node=end
    while node is not None:path.append(node);node=prev[node]
    path.reverse();segments=[]
    vias=[]
    for (la,ia,ja),(lb,ib,jb) in zip(path,path[1:]):
        if la!=lb:
            low=min(la,lb)
            entry=dict(name=f'VIA{low}{low+1}',x=xs[ia],y=ys[ja])
            if entry not in vias:vias.append(entry)
            continue
        line=dict(layer='M'+str(la),start=[xs[ia],ys[ja]],end=[xs[ib],ys[jb]])
        if segments and segments[-1]['layer']==line['layer'] and segments[-1]['end']==line['start']:
            segments[-1]['end']=line['end']
        else:segments.append(line)
    result=dict(status='clearance_plan_not_DRC_qualified',geometry=args.geometry,target=target,
                bounded_region=[x0,y0,x1,y1],states_examined=popped,cost=dist[end],
                segments=segments,vias=vias)
    with open(args.output,'x') as out:json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
