"""Legalize single-height T10 shell cells with sparse row interval occupancy.

Run with OpenROAD -python. This is a placement producer, not a substitute
for OpenROAD check_placement or the independent geometric overlap audit.
It preserves connectivity and fixed macros, uses actual ODB row fragments,
and writes a checkpoint before native validation to make recovery cheap.
"""

import argparse
import bisect
import json
import time
from collections import defaultdict
from pathlib import Path


def nearest_gap(occupied, count, span, target):
    """Return closest start of a span wholly inside unoccupied row sites."""
    cursor = 0
    best = None
    for start, end in [*occupied, (count, count)]:
        if start - cursor >= span:
            point = max(cursor, min(target, start - span))
            score = abs(point - target)
            if best is None or (score, point) < (best[0], best[1]):
                best = score, point
        cursor = max(cursor, end)
    return None if best is None else best[1]


def main():
    import odb

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_odb")
    parser.add_argument("output_odb")
    parser.add_argument("report_json")
    parser.add_argument("--row-stride", type=int, default=16)
    parser.add_argument("--padding-sites", type=int, default=1)
    args = parser.parse_args()
    if args.row_stride < 1 or args.padding_sites < 0:
        parser.error("row stride must be positive and padding nonnegative")
    started = time.monotonic()
    db = odb.dbDatabase.create()
    odb.read_db(db, args.input_odb)
    block = db.getChip().getBlock()
    dbu = block.getDbUnitsPerMicron()
    insts = list(block.getInsts())
    macros = [i for i in insts if i.getMaster().isBlock()]
    macro_before = [(i.getName(), i.getLocation(), str(i.getOrient())) for i in macros]
    cell_count_before = len(insts)
    net_count_before = len(block.getNets())
    if len(macros) != 16:
        raise RuntimeError(f"Expected sixteen tile macros, got {len(macros)}")
    for group in list(block.getGroups()):
        if group.getName().startswith("t10_top_channel_"):
            odb.dbGroup.destroy(group)
    for region in list(block.getRegions()):
        if region.getName().startswith("t10_top_channel_"):
            odb.dbRegion.destroy(region)
    rows = list(block.getRows())
    ys = sorted({row.getOrigin()[1] for row in rows})
    keep = set(ys[::args.row_stride]) | {ys[-1]}
    for row in rows:
        if row.getOrigin()[1] not in keep:
            odb.dbRow.destroy(row)
    rows = list(block.getRows())
    by_y = defaultdict(list)
    for row in rows:
        by_y[row.getOrigin()[1]].append(row)
    ys = sorted(by_y)
    occupied = defaultdict(list)
    cells = [i for i in insts if not i.getMaster().isBlock()]
    if any(i.isFixed() for i in cells):
        raise RuntimeError("This producer requires a movable pre-CTS shell")
    heights = {i.getMaster().getHeight() for i in cells}
    if len(heights) != 1:
        raise RuntimeError(f"Mixed-height shell unsupported: {heights}")
    height = next(iter(heights))
    if any(row.getSite().getHeight() != height for row in rows):
        raise RuntimeError("Row-site height differs from shell cell height")
    # Wider cells first reserve difficult gaps. Stable geometric ordering
    # keeps tied cells deterministic without depending on OpenDB iteration.
    cells.sort(key=lambda i: (-i.getMaster().getWidth(),
                             i.getBBox().yMin(), i.getBBox().xMin(), i.getName()))
    displacements = []
    selected_rows = {}
    for index, inst in enumerate(cells):
        box = inst.getBBox()
        x, y = box.xMin(), box.yMin()
        width = inst.getMaster().getWidth()
        insertion = bisect.bisect_left(ys, y)
        left, right = insertion - 1, insertion
        best = None
        while left >= 0 or right < len(ys):
            ld = abs(ys[left] - y) if left >= 0 else float("inf")
            rd = abs(ys[right] - y) if right < len(ys) else float("inf")
            if best is not None and min(ld, rd) > best[0]:
                break
            if ld <= rd:
                row_y = ys[left]
                left -= 1
            else:
                row_y = ys[right]
                right += 1
            for row in by_y[row_y]:
                ox, _ = row.getOrigin()
                pitch = row.getSpacing()
                if width % pitch:
                    raise RuntimeError(f"Cell width off site pitch: {inst.getName()}")
                span = width // pitch + 2 * args.padding_sites
                target = round((x - ox) / pitch) - args.padding_sites
                key = row.getName()
                start = nearest_gap(occupied[key], row.getSiteCount(), span, target)
                if start is None:
                    continue
                cell_x = ox + (start + args.padding_sites) * pitch
                distance = abs(cell_x - x) + abs(row_y - y)
                candidate = (distance, abs(row_y - y), cell_x, row_y, key,
                             start, span, row)
                if best is None or candidate[:5] < best[:5]:
                    best = candidate
        if best is None:
            raise RuntimeError(f"No remaining row capacity: {inst.getName()}")
        distance, _, cell_x, row_y, key, start, span, row = best
        bisect.insort(occupied[key], (start, start + span))
        inst.setOrient(str(row.getOrient()))
        inst.setLocation(cell_x, row_y)
        inst.setPlacementStatus("PLACED")
        actual = inst.getBBox()
        if (actual.xMin(), actual.yMin()) != (cell_x, row_y):
            raise RuntimeError(f"Unexpected transformed origin: {inst.getName()}")
        selected_rows[inst.getName()] = key
        displacements.append(distance / dbu)
        if index % 20000 == 0:
            print(f"T10_SPARSE_LEGALIZE cells={index}/{len(cells)} "
                  f"elapsed_s={time.monotonic()-started:.2f}", flush=True)
    if len(block.getInsts()) != cell_count_before or len(block.getNets()) != net_count_before:
        raise RuntimeError("Placement changed instance/net counts")
    if [(i.getName(), i.getLocation(), str(i.getOrient())) for i in macros] != macro_before:
        raise RuntimeError("Placement changed fixed macro geometry")
    output = Path(args.output_odb)
    output.parent.mkdir(parents=True, exist_ok=True)
    odb.write_db(db, str(output))
    report = {"status": "produced_pending_native_validation",
              "cell_count": len(cells), "macro_count": len(macros),
              "row_count": len(rows), "row_stride": args.row_stride,
              "padding_sites": args.padding_sites,
              "net_count": net_count_before,
              "average_displacement_um": sum(displacements) / len(displacements),
              "maximum_displacement_um": max(displacements),
              "elapsed_seconds": time.monotonic() - started}
    Path(args.report_json).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
