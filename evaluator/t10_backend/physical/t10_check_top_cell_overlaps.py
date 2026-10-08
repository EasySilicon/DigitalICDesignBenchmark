#!/usr/bin/env python3
"""Check actual non-macro cell boxes exported from a T10 OpenDB checkpoint.

Coordinates are integer DBU. Positive-area intersections are violations;
shared edges are legal. This geometric check supplements OpenDP's site and
row checks and does not replace them.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def audit(path: Path, bin_dbu: int) -> dict:
    bins = defaultdict(list)
    affected = set()
    pairs = 0
    cells = 0
    examples = []
    for line in path.read_text().splitlines():
        name, *coords = line.split()
        x0, y0, x1, y1 = map(int, coords)
        if x0 >= x1 or y0 >= y1:
            raise ValueError(f"Invalid cell box: {name}")
        seen = set()
        for gx in range(x0 // bin_dbu, (x1 - 1) // bin_dbu + 1):
            for gy in range(y0 // bin_dbu, (y1 - 1) // bin_dbu + 1):
                bucket = bins[gx, gy]
                for other, a, b, c, d in bucket:
                    if other in seen:
                        continue
                    seen.add(other)
                    if x0 < c and x1 > a and y0 < d and y1 > b:
                        pairs += 1
                        affected.update((name, other))
                        if len(examples) < 12:
                            examples.append([name, other])
                bucket.append((name, x0, y0, x1, y1))
        cells += 1
    return {"cell_count": cells, "cell_overlap_pairs": pairs,
            "overlapping_cells": len(affected), "examples": examples,
            "passed": pairs == 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boxes", type=Path)
    parser.add_argument("--bin-dbu", type=int, default=2000)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.bin_dbu <= 0:
        parser.error("--bin-dbu must be positive")
    report = audit(args.boxes, args.bin_dbu)
    encoded = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(encoded)
    print(encoded, end="")
    raise SystemExit(0 if report["passed"] else 1)
