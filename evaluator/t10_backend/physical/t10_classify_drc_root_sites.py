#!/usr/bin/env python3
"""Join net-only marker evidence to preclustered DRC root sites.

This is engineering triage only. It does not waive a marker or replace a full
ASAP7 signoff-deck run.
"""
import collections
import json
import sys

root_path, fixed_path, union_path, output_path = sys.argv[1:5]
roots = json.load(open(root_path))["net_only_sites"]
fixed = json.load(open(fixed_path))["records"]
union = json.load(open(union_path))["records"]


def box_gap(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return max(dx, dy)


def belongs(record, site):
    return (
        record["layer"] == site["layer"]
        and record["net"] in site["nets"]
        and box_gap(record["bbox_dbu"], site["bbox_union_dbu"]) <= 1
    )


sites = []
for site_index, site in enumerate(roots, 1):
    fixed_records = [record for record in fixed if belongs(record, site)]
    union_records = [record for record in union if belongs(record, site)]
    has_min_width = "Min Width" in site["rules"]
    fixed_hits = [
        hit
        for record in fixed_records
        for hit in record.get("fixed_shape_hits_within_100dbu", [])
    ]
    min_fixed_gap = min((hit["gap_dbu"] for hit in fixed_hits), default=None)
    direct_union = []
    nearby_union = []
    for record in union_records:
        for rule, distance in record.get(
            "nearest_merged_rule_violation_dbu", {}
        ).items():
            if distance is not None:
                nearby_union.append((rule, distance))
                if distance == 0:
                    direct_union.append((rule, distance))
    if has_min_width:
        classification = "actual_min_width"
    elif direct_union:
        classification = "actual_same_net_union_rule"
    elif fixed_hits:
        classification = "fixed_geometry_review"
    else:
        classification = "clean_after_same_net_union"
    sites.append(
        {
            **site,
            "site_index": site_index,
            "classification": classification,
            "non_min_marker_records": len(fixed_records),
            "union_records": len(union_records),
            "min_fixed_shape_gap_dbu": min_fixed_gap,
            "direct_union_violations": direct_union,
            "nearest_union_violation_dbu": min(
                (distance for _, distance in nearby_union), default=None
            ),
        }
    )

site_categories = collections.Counter(site["classification"] for site in sites)
marker_categories = {
    category: sum(
        site["marker_count"]
        for site in sites
        if site["classification"] == category
    )
    for category in sorted(site_categories)
}
result = {
    "method": (
        "Root-site join; Min Width retained; KLayout merged same-net rule "
        "violation only when distance=0; fixed geometry review when an "
        "obstruction or pin is within 100 DBU. Engineering triage only, not waiver."
    ),
    "summary": {
        "site_categories": dict(site_categories),
        "marker_categories": marker_categories,
    },
    "sites": sites,
}
with open(output_path, "w") as output:
    json.dump(result, output, indent=2, sort_keys=True)
    output.write("\n")
print(json.dumps(result["summary"], indent=2, sort_keys=True))
