"""Refresh edited signal routes in a diagnostic region after full invariant proof.

All other signal routes, placements/masters/OBS/pins must match the original
snapshot according to the supplied audit. Special-route geometry is compared
explicitly in the region as well. This only writes diagnostic JSON, never ODB.
"""
import argparse
import hashlib
import json
from pathlib import Path
import odb
from full_geometry import POLICY,wire_shapes
from special_geometry import special_shapes


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(4194304),b''):h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('geometry',type=Path);p.add_argument('audit',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();d=json.loads(a.geometry.read_text());audit=json.loads(a.audit.read_text())
    if a.output.exists():raise ValueError('output exists')
    if not d.get('special_routes_included') or audit.get('status')!='passed' or audit.get('wire_iterator_policy')!=POLICY:
        raise ValueError('complete geometry and full invariant proof are mandatory')
    if Path(d['odb']).resolve()!=Path(audit['before']['path']).resolve() or sha(d['odb'])!=audit['before']['sha256']:
        raise ValueError('original diagnostic source mismatch')
    candidate=Path(audit['after']['path'])
    if sha(candidate)!=audit['after']['sha256']:raise ValueError('candidate changed after audit')
    region=d['region']
    def local(s):
        b=s['bbox'];return b[0]<=region[2] and b[2]>=region[0] and b[1]<=region[3] and b[3]>=region[1]
    def special_key(s):return s['kind'],s.get('net'),s['layer'],tuple(s['bbox']),s.get('via'),tuple(s.get('origin',()))
    db=odb.dbDatabase.create();odb.read_db(db,str(candidate));block=db.getChip().getBlock()
    old_pg=sorted(special_key(s) for s in d['shapes'] if s['kind'].startswith('special_'))
    new_pg=[]
    for net in block.getNets():
        new_pg.extend(special_key(s) for s in special_shapes(net,region=region) if local(s))
    if old_pg!=sorted(new_pg):raise ValueError('special routing changed or diagnostic coverage differs')
    changed=set(audit['changed_nets'])
    shapes=[s for s in d['shapes'] if not (s['kind'].startswith('route_') and s.get('net') in changed)]
    for name in sorted(changed):
        net=block.findNet(name)
        if not net:raise ValueError('edited net absent')
        shapes.extend(s for s in wire_shapes(net) if local(s))
    d.update(odb=str(candidate),shapes=shapes,source_geometry=str(a.geometry),
             refreshed_nets=sorted(changed),invariant_audit=str(a.audit),
             invariant_audit_sha256=sha(a.audit),special_routes_compared_equal=True)
    a.output.write_text(json.dumps(d,indent=2)+'\n')
    print('REFRESHED',len(shapes),'shapes;',len(changed),'edited nets; special geometry unchanged')


if __name__=='__main__':main()
