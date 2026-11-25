"""Reconcile gate-SAIF aliases by electrical bit identity, never by guesses."""
import json, re, sys, time
from pathlib import Path
from t10_hybrid_ppa import REPO, artifact, check
sys.path.insert(0,str(REPO/'evaluator/t10_backend/v1'))
from merge_pe_saif import STAT

def normal(name):return name.replace('\\','').replace('/','.')

def aliases(module):
    result={}
    def add(name,bit):
        name=normal(name)
        if name in result and result[name]!=bit:raise ValueError('ambiguous normalized net alias: '+name)
        result[name]=bit
    for name,net in module['netnames'].items():
        bits=net['bits'];offset=net.get('offset',0);upto=net.get('upto',0)
        for index,bit in enumerate(bits):
            suffix=offset+(len(bits)-1-index if upto else index)
            add(name+'['+str(suffix)+']',bit)
            if len(bits)==1:add(name,bit)
    return result

def extract(source,lookup,pe_paths,output):
    stack=[];scopes=[];root=None;found=0;duration=None;scale=None;values={};unknown=[];alias_records=0;scope_cache={}
    pe_paths={normal(p) for p in pe_paths}
    with Path(source).open() as stream:
        for raw in stream:
            line=raw.strip()
            if line.startswith('(DURATION '):duration=int(line[10:-1])
            elif line.startswith('(TIMESCALE '):
                match=re.fullmatch(r'\(TIMESCALE (\d+)\s*(ps|ns|us|fs)\)',line)
                if not match:raise ValueError('unsupported SAIF timescale')
                scale=int(match[1])*dict(ps=1e-12,ns=1e-9,us=1e-6,fs=1e-15)[match[2]]
            elif line.startswith('(INSTANCE '):
                scopes.append(line[10:].replace('\\',''));stack.append('INSTANCE')
                if scopes==['tb_hidden_T10_stream','dut'] or scopes==['TOP','tb_hidden_T10_stream','dut']:
                    root=list(scopes);found+=1
            elif line in ['(NET','(SAIFILE']:stack.append(line[1:])
            elif line==')':
                if not stack:raise ValueError('unbalanced SAIF')
                if stack.pop()=='INSTANCE':scopes.pop()
            elif root and scopes[:len(root)]==root and line.startswith('('):
                scope_key=tuple(scopes[len(root):])
                if scope_key not in scope_cache:
                    relative=normal('.'.join(scope_key))
                    scope_cache[scope_key]=(relative,any(relative==p or relative.startswith(p+'.') for p in pe_paths))
                relative,skip=scope_cache[scope_key]
                if skip:continue
                match=STAT.fullmatch(line)
                if not match or not duration or not scale:raise ValueError('invalid peripheral SAIF record')
                name,t0,t1,tz,tx,tb,tc=match.groups();name=normal((relative+'.' if relative else '')+name)
                row=tuple(map(int,[t0,t1,tz,tx,tb,tc]))
                if row[0]+row[1]!=duration or any(row[2:5]):raise ValueError('invalid residency/unknown activity')
                if name not in lookup:
                    unknown.append(name);continue
                bit=lookup[name]
                if bit in values and values[bit]!=row:raise ValueError('electrically equivalent aliases have different activity: '+name)
                values[bit]=row;alias_records+=1
    if stack or scopes or found!=1 or not values:raise ValueError('incomplete DUT activity')
    output.write_text(json.dumps({'duration_seconds':duration*scale,'duration_ticks':duration,'seconds_per_tick':scale,
       'activity':{str(k):list(v) for k,v in values.items()},'source_alias_records':alias_records,
       'unmatched_saif_records':len(unknown),'unmatched_examples':unknown[:30]},indent=2)+'\n')
    return dict(duration_seconds=duration*scale,bits=len(values),unmatched_saif_records=len(unknown),unmatched_examples=unknown[:30])

def main(binding):
    started=time.monotonic();d=json.loads(Path(binding).read_text());out=Path(binding).parent
    graph=json.loads((out/'graph_input.json').read_text())
    if graph['source_sha256']!=d['source_sha256'] or graph['mapped_shell']!=d['shell']:raise ValueError('electrical graph source mismatch')
    check(graph['producer_inputs']);check(graph['graph'])
    source=Path(graph['graph']['path'])
    modules=json.loads(source.read_text())['modules'];top=modules['npu_systolic_matmul_16x16']
    lookup=aliases(top);del modules,top
    result=extract(out/'peripheral_activity/activity.saif',lookup,d['pe_paths'],out/'activity_bits.json')
    # Match the linked, unmodified shell's net names through Yosys bit identities.
    observed={};native_names=[]
    table=out/'TT_power/native_nets.txt'
    for name in table.read_text().splitlines():
        if any(c in name for c in '{}\r\n'):raise ValueError('unsupported Tcl-list net name')
        key=normal(name)
        if key not in lookup:raise ValueError('native net has no electrical source alias: '+name)
        if name in observed:raise ValueError('duplicate native net name')
        observed[name]=lookup[key];native_names.append(name)
    values=json.loads((out/'activity_bits.json').read_text());rows=values['activity'];duration=values['duration_seconds'];ticks=values['duration_ticks']
    missing=[]
    with (out/'activity_nets.tsv').open('x') as stream:
        for name,bit in observed.items():
            row=rows.get(str(bit))
            if row is None:
                if bit in ['0','1']:row=[ticks if bit=='0' else 0,ticks if bit=='1' else 0,0,0,0,0]
                else:missing.append(name);continue
            stream.write('{'+name+'} '+format(row[5]/duration,'.17g')+' '+format(row[1]/ticks,'.17g')+'\n')
    result.update(native_nets=len(native_names),missing_native_activity=len(missing),missing_examples=missing[:30],
      elapsed_seconds=time.monotonic()-started,source_graph=artifact(source),script=artifact(__file__))
    (out/'activity_mapping.json').write_text(json.dumps(result,indent=2)+'\n')
    if missing:raise ValueError('missing native activity, see mapping report')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main(sys.argv[1])
