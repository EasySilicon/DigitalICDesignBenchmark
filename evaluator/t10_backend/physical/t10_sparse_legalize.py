import argparse
import bisect
import collections
import json
import time
import odb

parser = argparse.ArgumentParser()
parser.add_argument('input_odb')
parser.add_argument('output_odb')
parser.add_argument('report_json')
args = parser.parse_args()
start = time.monotonic()
db = odb.dbDatabase.create()
odb.read_db(db, args.input_odb)
block = db.getChip().getBlock()
rows_by_y = collections.defaultdict(list)
for row in block.getRows():
    x, y = row.getOrigin()
    pitch = row.getSpacing()
    count = row.getSiteCount()
    rows_by_y[y].append((x, x + pitch * count, pitch, count, str(row.getOrient())))
ys = sorted(rows_by_y)
for y in ys:
    rows_by_y[y].sort(key=lambda entry: entry[0])
placements = {}
occupancy = collections.defaultdict(list)
movables = []
for inst in block.getInsts():
    if str(inst.getPlacementStatus()) == 'PLACED':
        bbox = inst.getBBox()
        width = inst.getMaster().getWidth()
        height = inst.getMaster().getHeight()
        if height != 270 or width % 54:
            raise RuntimeError(f'unsupported master geometry {inst.getName()} {width}x{height}')
        movables.append((bbox.yMin(), bbox.xMin(), inst, width))
movables.sort(key=lambda entry: (entry[0], entry[1]))
print('loaded', len(ys), 'physical rows', len(block.getRows()), 'segments', len(movables), 'movables', flush=True)

def best_in_segment(segment, occupied, wanted_x, width):
    x0, x1, pitch, count, orient = segment
    need = width // pitch
    if need > count:
        return None
    wanted = round((wanted_x - x0) / pitch)
    best = None
    previous = 0
    for left, right in occupied:
        high = left - need
        if previous <= high:
            candidate = max(previous, min(high, wanted))
            distance = abs(x0 + candidate * pitch - wanted_x)
            if best is None or distance < best[0]:
                best = (distance, candidate)
        previous = max(previous, right)
    high = count - need
    if previous <= high:
        candidate = max(previous, min(high, wanted))
        distance = abs(x0 + candidate * pitch - wanted_x)
        if best is None or distance < best[0]:
            best = (distance, candidate)
    return best

max_dx = max_dy = 0
sum_dx = sum_dy = 0
for n, (target_y, target_x, inst, width) in enumerate(movables, 1):
    pos = bisect.bisect_left(ys, target_y)
    candidates = []
    for delta in range(-3, 4):
        index = pos + delta
        if 0 <= index < len(ys):
            y = ys[index]
            for segment_index, segment in enumerate(rows_by_y[y]):
                x0, x1, pitch, count, orient = segment
                if x1 + 5400 < target_x or x0 - 5400 > target_x:
                    continue
                occupied = occupancy[(y, segment_index)]
                choice = best_in_segment(segment, occupied, target_x, width)
                if choice is not None:
                    dx, site = choice
                    candidates.append((dx + abs(y - target_y), dx, abs(y - target_y), y, segment_index, site, orient))
    if not candidates:
        # Global placement may put a cell inside a macro blockage. Expand
        # the search only for such cells; most cells use the local row.
        for radius in (8, 16, 32, 64):
            for delta in range(-radius, radius + 1):
                index = pos + delta
                if 0 <= index < len(ys):
                    y = ys[index]
                    for segment_index, segment in enumerate(rows_by_y[y]):
                        occupied = occupancy[(y, segment_index)]
                        choice = best_in_segment(segment, occupied, target_x, width)
                        if choice is not None:
                            dx, site = choice
                            candidates.append((dx + abs(y - target_y), dx, abs(y - target_y), y, segment_index, site, segment[4]))
            if candidates:
                break
    if not candidates:
        raise RuntimeError(f'no row site for {inst.getName()} at {(target_x, target_y)}')
    _, dx, dy, y, segment_index, site, orient = min(candidates)
    segment = rows_by_y[y][segment_index]
    x = segment[0] + site * segment[2]
    end_site = site + width // segment[2]
    occupied = occupancy[(y, segment_index)]
    bisect.insort(occupied, (site, end_site))
    inst.setOrient(orient)
    inst.setLocation(x, y)
    placements[inst.getName()] = (x, y)
    max_dx = max(max_dx, dx)
    max_dy = max(max_dy, dy)
    sum_dx += dx
    sum_dy += dy
    if n % 100000 == 0:
        print('legalized', n, 'elapsed_s', round(time.monotonic() - start, 1), flush=True)

# Validate every occupied interval on a site-aligned, macro-free row segment.
for key, intervals in occupancy.items():
    y, segment_index = key
    segment = rows_by_y[y][segment_index]
    previous = 0
    for left, right in intervals:
        if left < previous or right > segment[3]:
            raise RuntimeError(f'overlap or boundary violation {key}: {left}..{right}')
        previous = right
report = {'movable_instances': len(movables), 'row_segments': len(block.getRows()),
          'occupied_segments': len(occupancy), 'max_dx_dbu': max_dx,
          'max_dy_dbu': max_dy, 'mean_dx_dbu': sum_dx/len(movables),
          'mean_dy_dbu': sum_dy/len(movables), 'elapsed_seconds': time.monotonic()-start}
print('report', json.dumps(report), flush=True)
odb.write_db(db, args.output_odb)
with open(args.report_json, 'w') as handle:
    json.dump(report, handle, indent=2)
    handle.write('\n')
print('saved', args.output_odb, flush=True)
