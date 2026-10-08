#!/usr/bin/env python3
"""Prove that no T10 hard-macro V1 geometry can interact across its boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import klayout.db as kdb


V1_REQUIRED_CLEARANCE_NM = 30.0


def artifact(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def extract_v1_block(source: str) -> str:
    newline = "\r\n" if "\r\n" in source else "\n"
    route_start = source.index("###   M1")
    route_end = source.index("#   ONGRID", route_start)
    route = source[route_start:route_end]
    start = route.index("###   V1")
    end = route.index("###   V2", start)
    return route[start:end].rstrip("\r\n") + newline


def box_values(box: kdb.Box) -> list[int]:
    return [box.left, box.bottom, box.right, box.top]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gds", required=True, type=Path)
    parser.add_argument("--expected-gds-sha256", required=True)
    parser.add_argument("--deck", required=True, type=Path)
    parser.add_argument("--expected-deck-sha256", required=True)
    parser.add_argument("--expected-v1-block-sha256", required=True)
    parser.add_argument("--top-cell", required=True)
    parser.add_argument("--macro-cell", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    for path in (args.gds, args.deck):
        if not path.is_file():
            parser.error(f"missing input: {path}")
    for label, digest in (
        ("--expected-gds-sha256", args.expected_gds_sha256),
        ("--expected-deck-sha256", args.expected_deck_sha256),
        ("--expected-v1-block-sha256", args.expected_v1_block_sha256),
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            parser.error(f"{label} must be lowercase SHA-256")
    if len(args.macro_cell) != len(set(args.macro_cell)):
        parser.error("--macro-cell values must be unique")

    failures: list[str] = []
    gds_record = artifact(args.gds)
    deck_record = artifact(args.deck)
    if gds_record["sha256"] != args.expected_gds_sha256:
        failures.append("GDS SHA-256 does not match the accepted PE GDS")
    if deck_record["sha256"] != args.expected_deck_sha256:
        failures.append("deck SHA-256 does not match the locked ASAP7 deck")
    observed_max_rule_distance_nm: float | None = None
    try:
        v1_block = extract_v1_block(args.deck.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        failures.append(f"cannot extract V1 rule block: {error}")
        v1_block_sha256 = None
    else:
        v1_block_sha256 = hashlib.sha256(v1_block.encode("utf-8")).hexdigest()
        if v1_block_sha256 != args.expected_v1_block_sha256:
            failures.append("V1 rule block SHA-256 does not match the locked block")
        numeric_rule_distances_nm = [
            float(value)
            for value in re.findall(r"([0-9]+(?:\.[0-9]+)?)\.nm", v1_block)
        ]
        observed_max_rule_distance_nm = (
            max(numeric_rule_distances_nm) if numeric_rule_distances_nm else None
        )
        if observed_max_rule_distance_nm is None or not math.isclose(
            observed_max_rule_distance_nm,
            V1_REQUIRED_CLEARANCE_NM,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            failures.append(
                "locked V1 block maximum numeric rule distance is "
                f"{observed_max_rule_distance_nm}, expected "
                f"{V1_REQUIRED_CLEARANCE_NM} nm"
            )

    layout = kdb.Layout()
    layout.read(str(args.gds))
    top = layout.cell(args.top_cell)
    if top is None:
        parser.error(f"missing top cell: {args.top_cell}")
    v1_layer = layout.find_layer(21, 0)
    if v1_layer is None or v1_layer < 0:
        parser.error("GDS has no V1 layer 21/0")
    placement_counts: Counter[str] = Counter()
    macro_names = set(args.macro_cell)
    for instance in top.each_inst():
        master = layout.cell(instance.cell_index).name
        if master in macro_names:
            placement_counts[master] += 1

    required_dbu = V1_REQUIRED_CLEARANCE_NM / (layout.dbu * 1000.0)
    records: list[dict[str, Any]] = []
    for name in args.macro_cell:
        cell = layout.cell(name)
        if cell is None:
            failures.append(f"missing macro cell {name}")
            continue
        if placement_counts[name] == 0:
            failures.append(f"macro cell {name} is not instantiated by top")
        boundary = cell.bbox()
        v1_bbox = cell.bbox(v1_layer)
        if boundary.empty() or v1_bbox.empty():
            failures.append(f"macro cell {name} has empty boundary or V1 bbox")
            continue
        margins_dbu = [
            v1_bbox.left - boundary.left,
            v1_bbox.bottom - boundary.bottom,
            boundary.right - v1_bbox.right,
            boundary.top - v1_bbox.top,
        ]
        margins_nm = [value * layout.dbu * 1000.0 for value in margins_dbu]
        minimum_nm = min(margins_nm)
        if any(value + 1e-9 < required_dbu for value in margins_dbu):
            failures.append(
                f"macro cell {name} V1 boundary clearance {minimum_nm:.3f} nm "
                f"is below {V1_REQUIRED_CLEARANCE_NM:.3f} nm"
            )
        records.append(
            {
                "name": name,
                "placement_count": placement_counts[name],
                "boundary_bbox_dbu": box_values(boundary),
                "v1_bbox_dbu": box_values(v1_bbox),
                "v1_edge_margins_dbu": margins_dbu,
                "v1_edge_margins_nm": margins_nm,
                "minimum_v1_boundary_clearance_nm": minimum_nm,
            }
        )

    result = {
        "status": "pass" if not failures else "fail",
        "policy": (
            "The locked V1 rule block has a 30 nm maximum interaction distance. "
            "Every V1 polygon in every placed hard-macro master must be at least "
            "30 nm inside the rectangular macro boundary; macro-interior and "
            "top-interconnect V1 DRC then form disjoint, complete coverage."
        ),
        "failures": failures,
        "required_clearance_nm": V1_REQUIRED_CLEARANCE_NM,
        "observed_max_rule_distance_nm": observed_max_rule_distance_nm,
        "dbu_um": layout.dbu,
        "top_cell": args.top_cell,
        "expected_sha256": {
            "gds": args.expected_gds_sha256,
            "deck": args.expected_deck_sha256,
            "v1_block": args.expected_v1_block_sha256,
        },
        "observed_v1_block_sha256": v1_block_sha256,
        "artifacts": {"gds": gds_record, "deck": deck_record},
        "macros": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
