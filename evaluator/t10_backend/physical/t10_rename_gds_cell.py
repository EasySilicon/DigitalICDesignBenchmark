#!/usr/bin/env python3
"""Rename one GDS cell while preserving the rest of the hierarchy."""

from __future__ import annotations

import argparse
from pathlib import Path

import klayout.db as kdb


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("old_name")
    parser.add_argument("new_name")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"missing input: {args.input}")

    layout = kdb.Layout()
    layout.read(str(args.input))
    cell = layout.cell(args.old_name)
    if cell is None:
        parser.error(f"missing cell: {args.old_name}")
    if layout.cell(args.new_name) is not None and args.new_name != args.old_name:
        parser.error(f"target cell already exists: {args.new_name}")
    cell.name = args.new_name
    args.output.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(args.output))
    top_names = sorted(cell.name for cell in layout.top_cells())
    print(
        f"T10_GDS_RENAME old={args.old_name} new={args.new_name} "
        f"cells={layout.cells()} top={','.join(top_names)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
