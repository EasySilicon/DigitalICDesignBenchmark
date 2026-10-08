#!/usr/bin/env python3
"""Create a hash-bound PE top-interconnect view for hierarchical DRC.

The output retains every top-level shape and non-macro instance.  The named
hard-macro cells remain instantiated at their original transforms, but their
contents are cleared.  Macro interiors are qualified from their original GDS
files; macro/top boundary interactions require separate context views.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import klayout.db as kdb


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def shape_count(layout: kdb.Layout, cell: kdb.Cell) -> int:
    return sum(cell.shapes(layer).size() for layer in layout.layer_indices())


def box_record(box: kdb.Box) -> list[int] | None:
    if box.empty():
        return None
    return [box.left, box.bottom, box.right, box.top]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--top-cell", required=True)
    parser.add_argument("--macro-cell", action="append", required=True)
    parser.add_argument("--output-top-interconnect", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"missing input: {args.input}")
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_input_sha256):
        parser.error("--expected-input-sha256 must be lowercase SHA-256")
    if len(args.macro_cell) != len(set(args.macro_cell)):
        parser.error("--macro-cell values must be unique")

    input_record = artifact(args.input)
    if input_record["sha256"] != args.expected_input_sha256:
        parser.error(
            "input SHA-256 is " + input_record["sha256"]
            + ", expected " + args.expected_input_sha256
        )

    layout = kdb.Layout()
    layout.read(str(args.input))
    top = layout.cell(args.top_cell)
    if top is None:
        parser.error(f"missing top cell: {args.top_cell}")
    top_names = sorted(cell.name for cell in layout.top_cells())
    if top_names != [args.top_cell]:
        parser.error(f"expected sole top cell {args.top_cell!r}, got {top_names}")

    macro_set = set(args.macro_cell)
    placements: list[dict[str, Any]] = []
    placement_counts: Counter[str] = Counter()
    original_top_direct_instances = sum(1 for _ in top.each_inst())
    original_top_direct_shapes = shape_count(layout, top)
    for instance in top.each_inst():
        master = layout.cell(instance.cell_index).name
        if master not in macro_set:
            continue
        placement_counts[master] += 1
        placements.append(
            {
                "master": master,
                "transform": str(instance.dcplx_trans),
                "bbox_dbu": box_record(instance.bbox()),
            }
        )
    missing_placements = sorted(macro_set - set(placement_counts))
    if missing_placements:
        parser.error("macro cells not instantiated by top: " + ", ".join(missing_placements))

    macro_records: list[dict[str, Any]] = []
    for name in args.macro_cell:
        cell = layout.cell(name)
        if cell is None:
            parser.error(f"missing macro cell: {name}")
        record = {
            "name": name,
            "placement_count": placement_counts[name],
            "original_bbox_dbu": box_record(cell.bbox()),
            "original_direct_instances": sum(1 for _ in cell.each_inst()),
            "original_direct_shapes": shape_count(layout, cell),
        }
        cell.clear()
        if sum(1 for _ in cell.each_inst()) != 0 or shape_count(layout, cell) != 0:
            raise RuntimeError(f"failed to clear macro cell {name}")
        macro_records.append(record)

    args.output_top_interconnect.parent.mkdir(parents=True, exist_ok=True)
    save_options = kdb.SaveLayoutOptions()
    save_options.set_format_from_filename(str(args.output_top_interconnect))
    # GDS creation/modification timestamps otherwise make two byte-identical
    # logical views hash differently, defeating reproducible input binding.
    save_options.gds2_write_timestamps = False
    save_options.write_context_info = False
    layout.write(str(args.output_top_interconnect), save_options)

    # Reload the serialized artifact so the manifest describes what another
    # tool will actually consume, rather than only the in-memory mutation.
    check = kdb.Layout()
    check.read(str(args.output_top_interconnect))
    check_top = check.cell(args.top_cell)
    if check_top is None:
        raise RuntimeError("serialized top-interconnect view lost its top cell")
    serialized_top_direct_instances = sum(1 for _ in check_top.each_inst())
    serialized_top_direct_shapes = shape_count(check, check_top)
    if serialized_top_direct_instances != original_top_direct_instances:
        raise RuntimeError(
            "serialized view changed the top direct-instance count: "
            f"{serialized_top_direct_instances} != {original_top_direct_instances}"
        )
    if serialized_top_direct_shapes != original_top_direct_shapes:
        raise RuntimeError(
            "serialized view changed the top direct-shape count: "
            f"{serialized_top_direct_shapes} != {original_top_direct_shapes}"
        )
    for name in args.macro_cell:
        cell = check.cell(name)
        if cell is None:
            raise RuntimeError(f"serialized view lost macro placeholder {name}")
        if sum(1 for _ in cell.each_inst()) or shape_count(check, cell):
            raise RuntimeError(f"serialized macro placeholder {name} is not empty")

    result = {
        "schema_version": 1,
        "generator": artifact(Path(__file__)),
        "method": (
            "retain all top-level geometry and every non-macro hierarchy; "
            "clear only the named hard-macro cell contents while retaining "
            "their original top-level instances and transforms"
        ),
        "coverage_policy": {
            "this_view": "top interconnect and non-macro hierarchy",
            "separate_required_views": [
                "each original macro GDS interior",
                "each placed macro/top boundary interaction with rule-complete context",
            ],
            "no_waiver": True,
        },
        "dbu_um": layout.dbu,
        "top_cell": args.top_cell,
        "top_preservation": {
            "original_direct_instances": original_top_direct_instances,
            "serialized_direct_instances": serialized_top_direct_instances,
            "original_direct_shapes": original_top_direct_shapes,
            "serialized_direct_shapes": serialized_top_direct_shapes,
        },
        "input": input_record,
        "output_top_interconnect": artifact(args.output_top_interconnect),
        "macros": macro_records,
        "placements": sorted(
            placements,
            key=lambda item: (item["master"], item["bbox_dbu"] or []),
        ),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
