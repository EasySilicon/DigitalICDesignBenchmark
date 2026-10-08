"""Experimental ODB placement of final result hop FFs beside each bank.

This is a placement diagnosis, not a qualified physical implementation.
"""

import argparse
import collections
import json
import re

import odb


parser = argparse.ArgumentParser()
parser.add_argument('input_odb')
parser.add_argument('output_odb')
parser.add_argument('report_json')
args = parser.parse_args()

db = odb.dbDatabase.create()
odb.read_db(db, args.input_odb)
block = db.getChip().getBlock()
insts = list(block.getInsts())
dbu = block.getDbUnitsPerMicron()
rows = list(block.getRows())

pattern = re.compile(
    r'result_row\\\[(\d)\\\]\.result_cell\\\[(\d)\\\]\.'
    r'(data_pipe|slot_pipe|valid_pipe)\\\[(\d)\\\]'
)
final_stage = {0: 3, 1: 2, 2: 1}
by_row = collections.defaultdict(list)
for inst in insts:
    m = pattern.search(inst.getName())
    if m:
        row, col, kind, stage = m.groups()
        row, col, stage = int(row), int(col), int(stage)
        if col in final_stage and stage == final_stage[col]:
            by_row[row].append((col, kind, inst))

for row, entries in by_row.items():
    if len(entries) != 135:
        raise RuntimeError(f'row {row}: expected 132 final-hop FFs, got {len(entries)}')

locked = []
for inst in insts:
    if str(inst.getPlacementStatus()) in ('LOCKED', 'FIRM'):
        bbox = inst.getBBox()
        if bbox.xMax() > 1917 * dbu and bbox.xMin() < 1949 * dbu:
            locked.append((bbox.xMin(), bbox.yMin(), bbox.xMax(), bbox.yMax()))

report = {'moved_count': 0, 'per_bank': {}, 'dbu_per_micron': dbu}
for bank_row in range(4):
    bank = block.findInst(f'result_row\\[{bank_row}\\].bank')
    if bank is None:
        raise RuntimeError(f'missing bank {bank_row}')
    bank_bbox = bank.getBBox()
    bank_y = bank_bbox.yMin()
    bank_rows = sorted(
        (r for r in rows if abs(r.getOrigin()[1] - bank_y) < 9 * dbu and r.getOrigin()[0] < 1946 * dbu and r.getOrigin()[0] + r.getSpacing() * r.getSiteCount() > 1930 * dbu),
        key=lambda r: abs(r.getOrigin()[1] - bank_y),
    )
    selected = bank_rows[:14]
    selected.sort(key=lambda r: r.getOrigin()[1])
    available = []
    for physical_row in selected:
        origin_x, y = physical_row.getOrigin()
        pitch = physical_row.getSpacing()
        x0 = max(origin_x, 1929 * dbu)
        x1 = min(origin_x + pitch * physical_row.getSiteCount(), 1948 * dbu)
        sites = []
        x = origin_x + ((x0 - origin_x + pitch - 1) // pitch) * pitch
        while x + 1350 < x1:
            blocked = any(
                x < fx1 and x + 1350 > fx0 and y < fy1 and y + 270 > fy0
                for fx0, fy0, fx1, fy1 in locked
            )
            if not blocked:
                sites.append(x)
            x += pitch
        available.append((physical_row, sites))
    print('bank',bank_row,'row',physical_row.getName(),'y',y/dbu,'sites',len(sites),'locked',len(locked))
    occupied = collections.defaultdict(list)
    entries = sorted(by_row[bank_row], key=lambda item: (item[0], item[1], item[2].getName()))
    for index, (col, kind, inst) in enumerate(entries):
        width = inst.getMaster().getWidth()
        height = inst.getMaster().getHeight()
        if height != 270:
            raise RuntimeError(f'unexpected FF height {inst.getName()} {height}')
        # Rotate through rows so each column and bit spreads over the bank edge.
        row_order = [(index + offset) % len(available) for offset in range(len(available))]
        candidates = []
        for idx in row_order:
            physical_row, sites = available[idx]
            y = physical_row.getOrigin()[1]
            for x in sites:
                if x + width >= 1949 * dbu:
                    break
                if all(x + width <= other_x or x >= other_x + other_w
                       for other_x, other_w in occupied[idx]):
                    candidates.append((len(occupied[idx]), abs(y - bank_y), x, idx))
                    break
        if not candidates:
            raise RuntimeError(f'no site beside bank {bank_row} for {inst.getName()}')
        _, _, x, idx = min(candidates)
        physical_row = available[idx][0]
        y = physical_row.getOrigin()[1]
        inst.setOrient(str(physical_row.getOrient()))
        inst.setLocation(x, y)
        inst.setPlacementStatus('FIRM')
        occupied[idx].append((x, width))
        report['moved_count'] += 1
    report['per_bank'][str(bank_row)] = {
        'count': len(entries),
        'bank_y_um': bank_y / dbu,
        'rows_used': sum(bool(v) for v in occupied.values()),
        'x_span_um': [1918, 1949],
    }

odb.write_db(db, args.output_odb)
with open(args.report_json, 'w') as handle:
    json.dump(report, handle, indent=2)
    handle.write('\n')
print(json.dumps(report, indent=2))
