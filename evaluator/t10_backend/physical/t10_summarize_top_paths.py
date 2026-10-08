"""Summarize complete-DUT STA path families without accepting a PPA score."""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
POINT = re.compile(r'^\s*((?:' + NUMBER + r'\s+)+)[v^]\s+(.+)$')


def family(name):
    return re.sub(r'\$_\w+_$', '', re.sub(r'\[\d+\]', '[*]', name))


def parse_paths(text, scope):
    paths = []
    for chunk in text.split('Startpoint: ')[1:]:
        endpoint = re.search(r'^Endpoint: (.+)$', chunk, re.M)
        slack = re.search(r'^\s*(' + NUMBER + r')\s+slack \((?:VIOLATED|MET)\)', chunk, re.M)
        arrival = re.search(r'^\s*(' + NUMBER + r')\s+data arrival time', chunk, re.M)
        if not endpoint or not slack or not arrival:
            raise ValueError(f'Incomplete STA path in {scope}')
        start = chunk.splitlines()[0].strip()
        end = endpoint.group(1).strip()
        data = chunk.split('data arrival time', 1)[0]
        previous = None
        totals = defaultdict(float)
        counts = defaultdict(int)
        legs = []
        cells = []
        for line in data.splitlines():
            match = POINT.match(line)
            if not match:
                continue
            numbers = [float(v) for v in match.group(1).split()]
            delay, at = numbers[-2:]
            description = match.group(2)
            pin = description.split(' (', 1)[0]
            master_match = re.search(r'\(([^()]*)\)$', description)
            master = master_match.group(1) if master_match else ''
            instance = pin.rsplit('/', 1)[0] if '/' in pin else pin
            if previous is None:
                previous = (instance, pin, at)
                continue
            kind = 'wire' if instance != previous[0] else (
                'buffer' if master.startswith('BUFx') else
                'inverter' if master.startswith('INVx') else
                'macro_arc' if master == 't10_reference_tile_4x4' else 'logic_arc')
            totals[kind] += delay
            counts[kind] += 1
            if kind == 'wire':
                legs.append({'from': previous[1], 'to': pin, 'delay_ps': delay})
            else:
                cells.append({'instance': instance, 'master': master, 'delay_ps': delay})
            previous = (instance, pin, at)
        record = {'scope': scope, 'startpoint': start, 'endpoint': end,
                  'family': family(start) + ' -> ' + family(end),
                  'slack_ps': float(slack.group(1)), 'arrival_ps': float(arrival.group(1)),
                  'delay_totals_ps': dict(totals), 'arc_counts': dict(counts),
                  'largest_wire_arcs': sorted(legs, key=lambda x: -x['delay_ps'])[:5],
                  'nonbuffer_cells': [c for c in cells if not c['master'].startswith(('BUFx','INVx'))]}
        paths.append(record)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit_root', type=Path)
    args = parser.parse_args()
    receipts, scopes, all_paths = [], {}, []
    for path in sorted(args.audit_root.glob('*_setup.rpt')):
        text = path.read_text()
        paths = parse_paths(text, path.stem)
        receipts.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        all_paths.extend(paths)
        scopes[path.stem] = {'reported_paths': len(paths),
                            'worst_slack_ps': min((p['slack_ps'] for p in paths), default=None)}
    if len(scopes) != 6:
        raise ValueError('Expected six complete-DUT path scopes')
    families = defaultdict(list)
    for path in all_paths:
        families[path['scope'], path['family']].append(path)
    ranked = sorted(({'scope': key[0], 'family': key[1], 'paths_in_sample': len(paths),
                      'worst': min(paths, key=lambda p: p['slack_ps'])}
                     for key, paths in families.items()), key=lambda f:f['worst']['slack_ps'])
    report = {'diagnostic_only': True, 'physical_qualification_passed': False,
              'timing_mode': 'ideal clocks, native placement parasitics, fixed 1000 ps SDC',
              'count_note': 'Reported endpoint samples, not total violating endpoints or TNS.',
              'delay_note': 'Native ps from report_checks; clock/macro model remains in raw reports.',
              'input_reports': receipts, 'scopes': scopes, 'ranked_families': ranked,
              'paths': sorted(all_paths, key=lambda p:p['slack_ps'])}
    (args.audit_root/'path_families.json').write_text(json.dumps(report, indent=2)+'\n')
    md = ['# Full-DUT critical path audit', '',
          'Diagnostic placement STA only; full 16-tile / 256-PE scope, 1 GHz. No CTS or routed PPA qualification.', '',
          '| Scope | Reported endpoint samples | Worst setup slack (ps) |',
          '| --- | ---: | ---: |']
    for scope, result in scopes.items():
        slack = result['worst_slack_ps']
        md.append(f"| {scope} | {result['reported_paths']} | {slack if slack is not None else 'No timing path'} |")
    md += ['', '## Worst sampled path families', '',
           '| Family | Slack ps | Wire ps | Buffer ps | Logic + inverter ps |',
           '| --- | ---: | ---: | ---: | ---: |']
    for result in ranked[:15]:
        p=result['worst']; d=p['delay_totals_ps']
        md.append(f"| `{result['family']}` | {p['slack_ps']:.2f} | {d.get('wire',0):.2f} | {d.get('buffer',0):.2f} | {d.get('logic_arc',0)+d.get('inverter',0):.2f} |")
    md += ['', 'Counts are samples of reported endpoints, not TNS or the full endpoint population.', '']
    (args.audit_root/'critical_paths.md').write_text('\n'.join(md))
    print(json.dumps({'scopes':scopes, 'top_families':[{'family':r['family'],'worst_slack_ps':r['worst']['slack_ps']} for r in ranked[:8]]},indent=2))


if __name__ == '__main__':
    main()
