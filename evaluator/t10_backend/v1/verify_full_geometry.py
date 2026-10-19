"""Require complete RECT-aware connectivity for all six physical blocks."""
import argparse
import json
from pathlib import Path
import os

from resume_after_oom import artifact
from run_layout import HERE, REPO, run, sha

POLICY='OpenDB_paths_plus_explicit_RECT_decoder'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physical',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    physical=json.loads(args.physical.read_text()); output=args.output.resolve()
    if physical['status']!='single_seed_physical_qualified' or set(physical['blocks'])!={'fp0','fp1','fp2','int','cpa','pe'}:
        raise ValueError('all six blocks must first pass physical qualification')
    output.mkdir(parents=True,exist_ok=True)
    marker=output/'full_geometry.json'
    if marker.exists():
        saved=json.loads(marker.read_text())
        if saved['physical_sha256']!=sha(args.physical) or saved['checker_sha256']!=sha(Path(__file__)):
            raise ValueError('full-geometry proof has different input/checker; preserve it and select a new output')
        for key,record in saved['blocks'].items():
            path=Path(record['path'])
            data=json.loads(path.read_text())
            if sha(path)!=record['sha256'] or sha(Path(data['odb']['path']))!=data['odb']['sha256'] or \
                    data['checker_sha256']!=sha(HERE/'check_connectivity_full.py') or data['iterator_sha256']!=sha(HERE/'full_geometry.py'):
                raise ValueError('full-geometry proof changed')
        print('REUSE full-geometry proof; actual input and checker hashes verified',flush=True)
        return
    records={}
    for key,block in physical['blocks'].items():
        source=block['inputs']['odb']; path=Path(source['path'])
        if sha(path)!=source['sha256']:
            raise ValueError('physical checkpoint changed')
        result=output/(key+'.json')
        run(['openroad','-exit','-no_init','-python',str(HERE/'check_connectivity_full.py'),str(path),str(result)],
            output/(key+'.log'),os.environ,REPO)
        checked=json.loads(result.read_text())
        if checked['status']!='passed' or checked['wire_iterator_policy']!=POLICY or checked['odb']['sha256']!=source['sha256']:
            raise ValueError('incomplete or mismatched full geometry')
        records[key]=artifact(result)
    record=dict(status='single_seed_all_geometry_passed',layout_seed=physical['layout_seed'],wire_iterator_policy=POLICY,
                physical_sha256=sha(args.physical),checker_sha256=sha(Path(__file__)),blocks=records)
    marker.write_text(json.dumps(record,indent=2)+'\n')
    print('ALL SIX BLOCKS FULL GEOMETRY PASSED',physical['layout_seed'],flush=True)


if __name__=='__main__':
    main()
