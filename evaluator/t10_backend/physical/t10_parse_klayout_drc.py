#!/usr/bin/env python3
"""Summarize an ASAP7 KLayout DRC report and correlate PE root sites.

The script deliberately keeps correlation separate from disposition.  A
geometric match says that an official-deck item is near an OpenROAD marker;
it does not waive either item or prove that the two tools implement the same
rule.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import klayout.db  # noqa: F401  # Registers geometry classes used by klayout.rdb.
import klayout.rdb as rdb


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def called(obj: object, name: str) -> Any:
    value = getattr(obj, name)
    return value() if callable(value) else value


def value_bbox(value: rdb.RdbItemValue) -> list[float] | None:
    """Return an RDB value bbox in micrometres, if it is geometric."""
    geometry = None
    for predicate, accessor in (
        ("is_box", "box"),
        ("is_edge", "edge"),
        ("is_edge_pair", "edge_pair"),
        ("is_polygon", "polygon"),
        ("is_path", "path"),
    ):
        if called(value, predicate):
            geometry = called(value, accessor)
            break
    if geometry is None:
        return None
    box = called(geometry, "bbox")
    return [
        float(called(box, "left")),
        float(called(box, "bottom")),
        float(called(box, "right")),
        float(called(box, "top")),
    ]


def union_bbox(boxes: Iterable[list[float]]) -> list[float] | None:
    boxes = list(boxes)
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def box_distance(a: list[float], b: list[float]) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def rule_layer(category: str) -> str | None:
    match = re.search(r"(?:^|[^A-Z0-9])(M[1-9]|V[0-9])(?:[._:]|$)", category.upper())
    return match.group(1) if match else None


def load_root_sites(root_path: Path, analysis_path: Path) -> list[dict[str, Any]]:
    roots = json.loads(root_path.read_text())
    analysis = json.loads(analysis_path.read_text())
    sites: list[dict[str, Any]] = []
    for index, site in enumerate(roots["net_only_sites"], 1):
        sites.append(
            {
                "id": f"net_only_{index:03d}",
                "source_class": "net_only",
                "layer": site["layer"],
                "nets": site["nets"],
                "bbox_um": [coordinate / 1000.0 for coordinate in site["bbox_union_dbu"]],
                "openroad_marker_count": site["marker_count"],
                "openroad_rules": site["rules"],
                "location_category": site["location_category"],
            }
        )
    two_net = [record for record in analysis["records"] if record["source_class"] == "two_net"]
    for index, marker in enumerate(two_net, 1):
        sites.append(
            {
                "id": f"two_net_{index:03d}",
                "source_class": "two_net",
                "layer": marker["layer"],
                "nets": marker["nets"],
                "bbox_um": marker["bbox_um"],
                "openroad_marker_count": 1,
                "openroad_rules": [marker["type"]],
                "location_category": marker["location_category"],
            }
        )
    if len(sites) != roots["root_sites"]["total"]:
        raise ValueError(
            f"constructed {len(sites)} sites, expected {roots['root_sites']['total']}"
        )
    return sites


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("root_sites", type=Path)
    parser.add_argument("openroad_analysis", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--near-um",
        type=float,
        default=0.05,
        help="maximum bbox distance for a nearby-site diagnostic (default: 0.05 um)",
    )
    args = parser.parse_args()

    for path in (args.report, args.root_sites, args.openroad_analysis):
        if not path.is_file():
            parser.error(f"missing input: {path}")

    roots = load_root_sites(args.root_sites, args.openroad_analysis)
    roots_by_layer: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for site in roots:
        roots_by_layer[site["layer"]].append(site)
    report = rdb.ReportDatabase()
    report.load(str(args.report))

    by_category: collections.Counter[str] = collections.Counter()
    by_cell: collections.Counter[str] = collections.Counter()
    by_layer: collections.Counter[str] = collections.Counter()
    geometry_item_count = 0
    nongeometry_item_count = 0
    matches: dict[str, list[dict[str, Any]]] = {site["id"]: [] for site in roots}

    for item_index, item in enumerate(report.each_item(), 1):
        category_object = report.category_by_id(called(item, "category_id"))
        cell_object = report.cell_by_id(called(item, "cell_id"))
        category_name = str(called(category_object, "name")).strip()
        category_description = str(called(category_object, "description")).strip()
        category = category_name
        if not category and category_description:
            category = category_description.split(":", 1)[0].strip()
        if not category:
            category = str(called(category_object, "path")).strip("' ") or "<unnamed>"
        cell = str(called(cell_object, "qname"))
        layer = rule_layer(f"{category} {category_description}")
        boxes = [box for value in item.each_value() if (box := value_bbox(value)) is not None]
        bbox = union_bbox(boxes)

        by_category[category] += 1
        by_cell[cell] += 1
        if layer:
            by_layer[layer] += 1
        if bbox is None:
            nongeometry_item_count += 1
            continue
        geometry_item_count += 1

        # Front-end layers have no relationship to OpenROAD routing markers.
        # Every metal/via rule in the locked deck carries its layer either in
        # the category name or description (including the blank-name M1.S.2
        # rule), so skipping an unclassified category avoids false matches.
        for site in roots_by_layer.get(layer or "", []):
            distance = box_distance(bbox, site["bbox_um"])
            if distance <= args.near_um:
                matches[site["id"]].append(
                    {
                        "report_item_index": item_index,
                        "category": category,
                        "category_description": category_description,
                        "cell": cell,
                        "category_layer": layer,
                        "bbox_um": bbox,
                        "bbox_distance_um": distance,
                        "overlaps_root_bbox": distance == 0.0,
                    }
                )

    site_records = []
    for site in roots:
        item_matches = sorted(
            matches[site["id"]],
            key=lambda row: (row["bbox_distance_um"], row["category"], row["report_item_index"]),
        )
        site_records.append(
            {
                **site,
                "official_exact_or_overlapping_item_count": sum(
                    row["overlaps_root_bbox"] for row in item_matches
                ),
                "official_nearby_item_count": len(item_matches),
                "official_matches": item_matches,
            }
        )

    output = {
        "status": "analysis_only_not_waiver",
        "method": {
            "report_coordinates": "micrometres from KLayout RDB geometry",
            "openroad_coordinates": "DBU converted at 0.001 um/DBU",
            "correlation": "same inferred metal/via layer and bbox distance <= near_um; categories with no inferable routing layer are excluded",
            "near_um": args.near_um,
            "warning": "geometric correlation is diagnostic and does not waive any DRC item",
        },
        "inputs": {
            "report": str(args.report.resolve()),
            "report_sha256": sha256(args.report),
            "root_sites": str(args.root_sites.resolve()),
            "root_sites_sha256": sha256(args.root_sites),
            "openroad_analysis": str(args.openroad_analysis.resolve()),
            "openroad_analysis_sha256": sha256(args.openroad_analysis),
        },
        "report_summary": {
            "total_items": int(report.num_items()),
            "geometry_items": geometry_item_count,
            "nongeometry_items": nongeometry_item_count,
            "category_count": len(by_category),
            "cell_count": len(by_cell),
            "items_by_category": dict(sorted(by_category.items())),
            "items_by_cell": dict(sorted(by_cell.items())),
            "items_by_inferred_layer": dict(sorted(by_layer.items())),
        },
        "correlation_summary": {
            "root_site_count": len(site_records),
            "sites_with_exact_or_overlapping_official_item": sum(
                record["official_exact_or_overlapping_item_count"] > 0 for record in site_records
            ),
            "sites_with_nearby_official_item": sum(
                record["official_nearby_item_count"] > 0 for record in site_records
            ),
            "net_only_sites_with_exact_or_overlapping_official_item": sum(
                record["source_class"] == "net_only"
                and record["official_exact_or_overlapping_item_count"] > 0
                for record in site_records
            ),
            "two_net_sites_with_exact_or_overlapping_official_item": sum(
                record["source_class"] == "two_net"
                and record["official_exact_or_overlapping_item_count"] > 0
                for record in site_records
            ),
        },
        "root_sites": site_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output["report_summary"], indent=2, sort_keys=True))
    print(json.dumps(output["correlation_summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
