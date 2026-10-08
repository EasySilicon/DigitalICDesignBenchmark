#!/usr/bin/env python3
"""Qualify a complete, disjoint set of hash-bound ASAP7 route DRC runs."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path
from typing import Any


EXPECTED_SECTIONS = [
    "M1", "M2", "M3", "V1", "V2", "V3", "M4", "M5", "V4", "V5",
    "M6", "M7", "V6", "V7", "M8", "M9", "V8", "V9",
]


def file_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def route_parts(source: str) -> tuple[str, str, dict[str, str]]:
    drc_marker = source.index("# DRC section")
    prefix_end = source.index("\n", drc_marker) + 1
    route_start = source.index("###   M1", prefix_end)
    route_end = source.index("#   ONGRID", route_start)
    footer_start = source.index("</text>", route_end)
    route_rules = source[route_start:route_end]
    matches = list(
        re.finditer(r"(?m)^###\s+(M[1-9]|V[1-9])\s*$", route_rules)
    )
    names = [match.group(1) for match in matches]
    if names != EXPECTED_SECTIONS:
        raise ValueError(f"unexpected official route section order: {names}")
    if route_rules.count(".output(") != 152:
        raise ValueError("official route block does not contain 152 output rules")
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(route_rules)
        blocks[match.group(1)] = route_rules[match.start():end]
    return source[:prefix_end], source[footer_start:], blocks


def normalize_execution_parameters(text: str) -> tuple[str, int, float]:
    normalized = text.replace("\r\n", "\n")
    thread_matches = re.findall(r"(?m)^\s*threads\((\d+)\)\s*$", normalized)
    tile_matches = re.findall(
        r"(?m)^\s*tiles\(([0-9]+(?:\.[0-9]+)?)\.um\)\s*$", normalized
    )
    if len(thread_matches) != 1 or len(tile_matches) != 1:
        raise ValueError("expected exactly one numeric threads() and tiles() statement")
    threads = int(thread_matches[0])
    tile_um = float(tile_matches[0])
    if threads < 1 or tile_um <= 0:
        raise ValueError("threads and tile size must be positive")
    normalized = re.sub(
        r"(?m)^\s*threads\(\d+\)\s*$", "threads(<EXECUTION_PARAMETER>)", normalized
    )
    normalized = re.sub(
        r"(?m)^\s*tiles\([0-9]+(?:\.[0-9]+)?\.um\)\s*$",
        "tiles(<EXECUTION_PARAMETER>)",
        normalized,
    )
    return normalized, threads, tile_um


def partition_sections(text: str) -> list[str]:
    return re.findall(r"(?m)^###\s+(M[1-9]|V[1-9])\s*$", text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-deck", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for path in (args.official_deck, args.manifest):
        if not path.is_file():
            parser.error(f"missing input: {path}")

    official_bytes = args.official_deck.read_bytes()
    official = official_bytes.decode("utf-8")
    prefix, footer, official_blocks = route_parts(official)
    manifest = json.loads(args.manifest.read_text())
    expected_gds_sha256 = str(manifest.get("expected_gds_sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_gds_sha256):
        parser.error("manifest expected_gds_sha256 must be a 64-digit lowercase SHA-256")
    entries = manifest.get("partitions")
    if not isinstance(entries, list) or not entries:
        parser.error("manifest partitions must be a nonempty list")

    failures: list[str] = []
    seen_sections: list[str] = []
    partition_records: list[dict[str, Any]] = []
    total_items = 0
    categories: collections.Counter[str] = collections.Counter()
    artifact_cache: dict[str, dict[str, Any]] = {}

    for index, entry in enumerate(entries, 1):
        label = f"partition {index}"
        try:
            deck_path = Path(entry["deck"])
            gate_path = Path(entry["gate_result"])
        except (KeyError, TypeError):
            failures.append(f"{label}: missing deck or gate_result path")
            continue
        if not deck_path.is_file() or not gate_path.is_file():
            failures.append(f"{label}: missing deck or gate result file")
            continue

        deck_record = file_record(deck_path)
        gate_record = file_record(gate_path)
        deck_text = deck_path.read_bytes().decode("utf-8")
        sections = partition_sections(deck_text)
        if not sections or len(sections) != len(set(sections)):
            failures.append(f"{label}: empty or internally repeated section list {sections}")
        canonical_sections = [name for name in EXPECTED_SECTIONS if name in sections]
        if sections != canonical_sections:
            failures.append(f"{label}: sections are not in locked canonical order")
        seen_sections.extend(sections)

        expected_text = prefix + "".join(official_blocks[name] for name in sections).rstrip("\r\n") + "\n" + footer
        try:
            normalized_actual, threads, tile_um = normalize_execution_parameters(deck_text)
            normalized_expected, _, _ = normalize_execution_parameters(expected_text)
        except ValueError as error:
            failures.append(f"{label}: {error}")
            threads = None
            tile_um = None
            normalized_actual = ""
            normalized_expected = "<invalid>"
        if normalized_actual != normalized_expected:
            failures.append(
                f"{label}: deck differs from the exact official selected sections "
                "outside threads/tile execution parameters"
            )

        gate = json.loads(gate_path.read_text())
        gate_failures = gate.get("failures", [])
        if gate.get("status") != "pass":
            failures.append(f"{label}: strict DRC gate did not pass")
        if gate_failures:
            failures.append(f"{label}: strict DRC gate has recorded failures")
        for artifact_name, recorded in gate.get("artifacts", {}).items():
            artifact_path_text = recorded.get("path") if isinstance(recorded, dict) else None
            if not artifact_path_text:
                failures.append(f"{label}: gate artifact {artifact_name} has no path")
                continue
            artifact_path = Path(artifact_path_text)
            cache_key = str(artifact_path.resolve())
            if cache_key not in artifact_cache:
                if artifact_path.is_file():
                    artifact_cache[cache_key] = file_record(artifact_path)
                else:
                    artifact_cache[cache_key] = {"path": cache_key, "missing": True}
            actual_record = artifact_cache[cache_key]
            if actual_record.get("missing"):
                failures.append(f"{label}: gate artifact {artifact_name} is missing")
            elif actual_record.get("sha256") != recorded.get("sha256"):
                failures.append(f"{label}: gate artifact {artifact_name} hash changed")
        actual_deck_sha = gate.get("artifacts", {}).get("deck", {}).get("sha256")
        actual_gds_sha = gate.get("artifacts", {}).get("gds", {}).get("sha256")
        expected_hashes = gate.get("expected_sha256", {})
        if actual_deck_sha != deck_record["sha256"]:
            failures.append(f"{label}: gate deck hash does not match the manifest deck")
        if expected_hashes.get("deck") != deck_record["sha256"]:
            failures.append(f"{label}: gate did not bind the actual partition deck hash")
        if actual_gds_sha != expected_gds_sha256:
            failures.append(f"{label}: gate GDS hash does not match the manifest GDS")
        if expected_hashes.get("gds") != expected_gds_sha256:
            failures.append(f"{label}: gate did not bind the manifest GDS hash")

        summary = gate.get("report_summary", {})
        items = int(summary.get("total_items", 0))
        if items != 0:
            failures.append(f"{label}: strict gate summary contains {items} DRC items")
        total_items += items
        categories.update(summary.get("items_by_category", {}))
        partition_records.append(
            {
                "index": index,
                "sections": sections,
                "output_rule_count": deck_text.count(".output("),
                "threads": threads,
                "tile_um": tile_um,
                "gate_status": gate.get("status"),
                "gate_failures": gate_failures,
                "drc_items": items,
                "deck": deck_record,
                "gate_result": gate_record,
            }
        )

    section_counts = collections.Counter(seen_sections)
    missing = [name for name in EXPECTED_SECTIONS if section_counts[name] == 0]
    repeated = {name: count for name, count in section_counts.items() if count != 1}
    unexpected = [name for name in section_counts if name not in EXPECTED_SECTIONS]
    if missing:
        failures.append(f"missing route sections: {missing}")
    if repeated:
        failures.append(f"route sections do not occur exactly once: {repeated}")
    if unexpected:
        failures.append(f"unexpected route sections: {unexpected}")
    output_rule_count = sum(record["output_rule_count"] for record in partition_records)
    if output_rule_count != 152:
        failures.append(f"partition set has {output_rule_count} output rules, expected 152")

    result = {
        "status": "pass" if not failures else "fail",
        "policy": (
            "all 18 route sections and all 152 output rules exactly once; section "
            "text identical to the locked deck; only positive threads/tile execution "
            "parameters may differ; every hash-bound strict DRC gate passes"
        ),
        "failures": failures,
        "expected_gds_sha256": expected_gds_sha256,
        "official_deck": file_record(args.official_deck),
        "manifest": file_record(args.manifest),
        "coverage": {
            "expected_sections": EXPECTED_SECTIONS,
            "observed_sections": seen_sections,
            "missing_sections": missing,
            "repeated_sections": repeated,
            "output_rule_count": output_rule_count,
        },
        "aggregate_drc": {
            "total_items": total_items,
            "items_by_category": dict(sorted(categories.items())),
        },
        "partitions": partition_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
