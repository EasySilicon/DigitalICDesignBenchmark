"""Archive small measured reports without rewriting their original provenance.

Requires the completed strict three-seed assembly. Large checkpoints/activity
remain external, with sizes and hashes; this is not a self-contained EDA image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

REPO=Path(__file__).resolve().parents[3]
SMALL_SUFFIXES={'.json','.rpt','.raw','.log','.sdc','.tcl','.py','.cc','.cpp','.mk','.lib','.tsv'}
MAX_BYTES=8*1024**2


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(4194304),b''):h.update(data)
    return h.hexdigest()


def verify_bundle(directory):
    directory=directory.resolve();index=json.loads((directory/'index.json').read_text())
    for row in index['portable']:
        path=(directory/row['path']).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or \
                path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:
            raise ValueError('portable artifact missing/changed: '+row['path'])
    for row in index['repository']:
        path=(REPO/row['path']).resolve()
        if not path.is_relative_to(REPO) or not path.is_file() or sha(path)!=row['sha256']:
            raise ValueError('repository dependency missing/changed: '+row['path'])
    return index


def export(evidence_path,work,output):
    evidence=json.loads(evidence_path.read_text())
    if evidence.get('measurement_status')!='three_seed_single_pe' or \
            evidence.get('measurement_scope')!='single_pe' or \
            [r['layout_seed'] for r in evidence.get('per_seed',[])]!=[11,29,47]:
        raise ValueError('completed three-seed assembly required')
    if output.exists():raise ValueError('bundle output already exists')
    records={};visited=set();archives={}
    for seed in evidence['per_seed']:
        record=seed['levels']['pe']['artifacts'].get('manual_repair')
        if record:
            manual=json.loads(Path(record['path']).read_text())
            invariant=json.loads(Path(manual['invariants']['path']).read_text())
            original=manual['original_artifacts']['6_final.odb']
            before=invariant['before']
            if any(before[k]!=original[k] for k in ('bytes','sha256')):
                raise ValueError('archived original differs from invariant before-image')
            archives[(str(Path(before['path']).resolve()),before['sha256'])]=Path(original['path']).resolve()
            marker=json.loads(Path(manual['original_completion_marker']['path']).read_text())
            for name,archived in manual['original_artifacts'].items():
                if any(archived[k]!=marker['artifacts'][name][k] for k in ('bytes','sha256')):
                    raise ValueError('archive differs from original completion marker')
                canonical=Path(marker['result_dir'])/name
                archives[(str(canonical.resolve()),archived['sha256'])]=Path(archived['path']).resolve()

    def add(path,digest=None,size=None):
        path=Path(path)
        if not path.is_absolute():
            # The frozen vector manifest predates repo-relative paths.
            path=REPO/('evaluator/make_t10_power_vectors.py' if str(path)=='make_t10_power_vectors.py' else path)
        path=path.resolve();original_path=path
        path=archives.get((str(path),digest),path)
        actual=path.stat().st_size
        if size is not None and size!=actual:raise ValueError('artifact size changed: '+str(path))
        small=path.suffix in SMALL_SUFFIXES and actual<=MAX_BYTES
        if digest is None:digest=sha(path)
        elif small and sha(path)!=digest:raise ValueError('artifact hash changed: '+str(path))
        row=dict(original_path=str(original_path),bytes=actual,sha256=digest)
        if path!=original_path:row['archived_path']=str(path)
        key=(str(original_path),digest)
        if key in records and records[key]!=row:raise ValueError('conflicting artifact claims')
        records[key]=row
        if path.suffix=='.json' and small and path not in visited:
            visited.add(path);walk(json.loads(path.read_text()))

    def walk(value):
        if isinstance(value,dict):
            if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
                add(value['path'],value['sha256'],value.get('bytes'))
            if {'report_path','report_sha256'}<=value.keys():
                add(value['report_path'],value['report_sha256'])
                if 'activity_net_data_sha256' in value:
                    add(Path(value['report_path']).parent/'activity_nets.tsv',value['activity_net_data_sha256'])
            # Macro abstracts already use nested artifact dictionaries; only
            # the standard-library map is keyed directly by filesystem path.
            for path,digest in value.get('tt_standard_libraries',{}).items():add(path,digest)
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)

    # These were created only after strict assembly validated every real seed.
    for p in (evidence_path,evidence_path.with_name('scoring_reference.json'),evidence_path.with_name('evaluator_inventory.json')):add(p)
    for path,digest in json.loads(evidence_path.with_name('evaluator_inventory.json').read_text()).items():
        add(REPO/path,digest)
    for seed in (11,29,47):
        root=work/f'seed{seed}_activity_directnets';manifest=json.loads((root/'activity_manifest.json').read_text())
        for name in ('activity_manifest.json','merge_audit.json','staged_build_manifest.json','simulation.log'):add(root/name)
        writer=manifest['saif_writer']
        add(writer['native_source'],writer['native_sha256'])
        add(root/'saif_window/t10_saif_window.cpp',writer['corrected_sha256'])
        add(root/'build/Vtb_hidden_T10_stream_windowed',writer['executable_sha256'])
        add(root/'activity.saif',manifest['activity_sha256'])
        merged=json.loads((root/'merge_audit.json').read_text())
        add(root/'average.saif',merged['output_sha256'])
        if seed!=11:add(work/f'seed{seed}_complete.json')
    index=dict(status='portable_reports_with_external_checkpoints',seeds=[11,29,47],
               portable=[],repository=[],external=[])
    for _,row in sorted(records.items()):
        path=Path(row.get('archived_path',row['original_path']))
        if path.is_relative_to(REPO):
            index['repository'].append(dict(row,path=str(path.relative_to(REPO))))
        elif path.suffix in SMALL_SUFFIXES and row['bytes']<=MAX_BYTES:
            index['portable'].append(dict(row,path='reports/'+row['sha256']+'_'+path.name))
        else:index['external'].append(row)
    # Validate all small sources above before creating the output directory.
    output.mkdir(parents=True)
    (output/'reports').mkdir()
    for row in index['portable']:shutil.copyfile(row.get('archived_path',row['original_path']),output/row['path'])
    (output/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    verify_bundle(output)
    print('PORTABLE REPORTS VERIFIED',len(index['portable']),'files;',len(index['external']),'external checkpoints/activity records')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path);parser.add_argument('--work',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--verify',type=Path)
    a=parser.parse_args()
    if a.verify:
        index=verify_bundle(a.verify);print('VERIFIED',len(index['portable']),'portable artifacts')
    elif a.evidence and a.work and a.output:export(a.evidence.resolve(),a.work.resolve(),a.output.resolve())
    else:parser.error('use --verify DIR, or --evidence FILE --work DIR --output DIR')
