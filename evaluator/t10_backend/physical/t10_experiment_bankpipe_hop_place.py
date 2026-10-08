"""Experimentally place 4x4 tile result-hop registers under the PE row.

The bank captures the final write hop. Remaining tile result hops are
placed near x=900/1450 um, matching the final PE-to-bank direction. This only generates an ODB for diagnosis.
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
dbu = block.getDbUnitsPerMicron()
rows = list(block.getRows())
insts = list(block.getInsts())

pattern = re.compile(
    r'result_row\\\[(\d)\\\]\.result_cell\\\[(\d)\\\]\.'
    r'(data_pipe|slot_pipe|valid_pipe)\\\[(\d)\\\]'
)
# The tested bank-input-pipe RTL leaves two tile stages in column 0 and one in column 1.
target_x_um = {(0, 1): 900, (0, 2): 1450, (1, 1): 1450}
groups = collections.defaultdict(list)
for inst in insts:
    match = pattern.search(inst.getName())
    if match:
        row, col, kind, stage = match.groups()
        key = (int(row), int(col), int(stage))
        if (key[1], key[2]) in target_x_um:
            groups[key].append(inst)
for row in range(4):
    for col, stage in target_x_um:
        if len(groups[row, col, stage]) != 44:
            raise RuntimeError(f'incomplete hop group {(row,col,stage)}: '
                               f'{len(groups[row,col,stage])}')

fixed_rects = []
for inst in insts:
    if str(inst.getPlacementStatus()) in ('LOCKED', 'FIRM'):
        rect = inst.getBBox()
        fixed_rects.append((rect.xMin(), rect.yMin(), rect.xMax(), rect.yMax()))

report = {'moved_count': 0, 'groups': {}, 'dbu_per_micron': dbu}
occupancy = collections.defaultdict(list)
for row in range(4):
    pe = block.findInst(f'pe_row\\[{row}\\].pe_col\\[0\\].pe')
    if pe is None:
        raise RuntimeError(f'missing PE row {row}')
    pe_bottom = pe.getBBox().yMin()
    target_y = pe_bottom - 10 * dbu
    for col, stage in target_x_um:
        target_x = target_x_um[col, stage] * dbu
        local_fixed = [rect for rect in fixed_rects
                       if rect[0] < target_x + 45 * dbu
                       and rect[2] > target_x - 2 * dbu
                       and rect[1] < pe_bottom
                       and rect[3] > pe_bottom - 20 * dbu]
        physical_rows = sorted(
            (r for r in rows
             if pe_bottom - 20 * dbu <= r.getOrigin()[1] < pe_bottom - 2 * dbu
             and r.getOrigin()[0] < target_x - 10 * dbu
             and r.getOrigin()[0] + r.getSpacing() * r.getSiteCount() > target_x + 20 * dbu),
            key=lambda r: abs(r.getOrigin()[1] - target_y),
        )[:18]
        if len(physical_rows) != 18:
            raise RuntimeError(f'row {row}: missing corridor rows at x={target_x/dbu}')
        ordered = sorted(groups[row, col, stage], key=lambda inst: inst.getName())
        for index, inst in enumerate(ordered):
            width, height = inst.getMaster().getWidth(), inst.getMaster().getHeight()
            if height != 270:
                raise RuntimeError(f'unexpected cell height {inst.getName()} {height}')
            candidates = []
            for idx, physical_row in enumerate(physical_rows):
                origin_x, y = physical_row.getOrigin()
                pitch = physical_row.getSpacing()
                x_start = origin_x + round((target_x - origin_x) / pitch) * pitch
                for offset in range(0, 500):
                    x = x_start + offset * pitch
                    if x + width >= origin_x + pitch * physical_row.getSiteCount():
                        break
                    if any(x < fx1 and x + width > fx0 and y < fy1 and y + height > fy0
                           for fx0, fy0, fx1, fy1 in local_fixed):
                        continue
                    if any(x < xx + ww and x + width > xx
                           for xx, ww in occupancy[(row, y)]):
                        continue
                    candidates.append((len(occupancy[(row, y)]), abs(y - target_y), x, idx))
                    break
            if not candidates:
                raise RuntimeError(f'no site for {inst.getName()}')
            _, _, x, idx = min(candidates)
            physical_row = physical_rows[idx]
            y = physical_row.getOrigin()[1]
            inst.setOrient(str(physical_row.getOrient()))
            inst.setLocation(x, y)
            inst.setPlacementStatus('FIRM')
            occupancy[(row, y)].append((x, width))
            report['moved_count'] += 1
        report['groups'][f'{row},{col},{stage}'] = {'count': len(ordered),
                                                    'target_x_um': target_x/dbu,
                                                    'target_y_um': target_y/dbu}

# The staggered-reset RTL shares a seven-stage shift spine. Its taps at
# stages 3..6 serve bank rows 0..3. Move them into the narrow corridor beside
# their bank so a shared control flop cannot end up hundreds of microns away.
guard_pattern = re.compile(r'reset_guard\\\[(\d)\\\]')
guards = {}
for inst in insts:
    match = guard_pattern.search(inst.getName())
    if match and inst.getMaster().getName().startswith('DFF'):
        stage = int(match.group(1))
        if stage in guards:
            raise RuntimeError(f'duplicate reset guard stage {stage}')
        guards[stage] = inst
if guards:
    if sorted(guards) != list(range(7)):
        raise RuntimeError(f'unexpected shared reset guard stages {sorted(guards)}')
    report['guard_positions'] = {}
    for stage, inst in sorted(guards.items()):
        bank_row = max(0, stage - 3)
        bank = block.findInst(f'result_row\\[{bank_row}\\].bank')
        bank_y = bank.getBBox().yMin()
        # The bank's row halo removes sites alongside its body. The nearest
        # legal corridor is immediately below the bank's bottom edge.
        target_y = bank_y - 3 * dbu
        width, height = inst.getMaster().getWidth(), inst.getMaster().getHeight()
        candidates = []
        for physical_row in rows:
            origin_x, y = physical_row.getOrigin()
            pitch = physical_row.getSpacing()
            if abs(y - target_y) > 6 * dbu:
                continue
            if not (origin_x < 1930 * dbu and
                    origin_x + pitch * physical_row.getSiteCount() > 1935 * dbu):
                continue
            start = origin_x + round((1930 * dbu - origin_x) / pitch) * pitch
            for site in range(150):
                x = start + site * pitch
                if x + width >= min(bank.getBBox().xMin(),
                                    origin_x + pitch * physical_row.getSiteCount()):
                    break
                if any(x < fx1 and x + width > fx0 and y < fy1 and y + height > fy0
                       for fx0, fy0, fx1, fy1 in fixed_rects):
                    continue
                if any(x < xx + ww and x + width > xx
                       for xx, ww in occupancy[(bank_row, y)]):
                    continue
                candidates.append((abs(y - target_y), abs(x - 1930 * dbu),
                                   x, y, physical_row))
                break
        if not candidates:
            raise RuntimeError(f'no bank-side reset-guard site for stage {stage}')
        _, _, x, y, physical_row = min(candidates)
        inst.setOrient(str(physical_row.getOrient()))
        inst.setLocation(x, y)
        inst.setPlacementStatus('FIRM')
        occupancy[(bank_row, y)].append((x, width))
        report['guard_positions'][str(stage)] = [x / dbu, y / dbu]
        report['moved_count'] += 1

odb.write_db(db, args.output_odb)
with open(args.report_json, 'w') as handle:
    json.dump(report, handle, indent=2)
    handle.write('\n')
print(json.dumps({'moved_count': report['moved_count'],
                  'groups': len(report['groups'])}))
