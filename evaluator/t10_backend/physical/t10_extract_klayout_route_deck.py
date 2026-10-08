#!/usr/bin/env python3
"""Extract the unchanged M1-M9/V1-V9 rule block from the locked ASAP7 deck."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--tile-um", type=float, default=100.0)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"missing input: {args.input}")
    if args.threads < 1 or args.tile_um <= 0:
        parser.error("--threads and --tile-um must be positive")

    source = args.input.read_text()
    drc_marker = source.index("# DRC section")
    prefix_end = source.index("\n", drc_marker) + 1
    route_start = source.index("###   M1", prefix_end)
    route_end = source.index("#   ONGRID", route_start)
    footer_start = source.index("</text>", route_end)
    route_rules = source[route_start:route_end].rstrip() + "\n"

    if route_rules.count(".output(") != 152:
        parser.error(
            f"locked route block changed: expected 152 output rules, found {route_rules.count('.output(')}"
        )
    sections = re.findall(r"(?m)^###\s+(M[1-9]|V[1-9])\s*$", route_rules)
    expected_sections = [
        "M1", "M2", "M3", "V1", "V2", "V3", "M4", "M5", "V4", "V5",
        "M6", "M7", "V6", "V7", "M8", "M9", "V8", "V9",
    ]
    if sections != expected_sections:
        parser.error(f"unexpected route section order: {sections}")

    prepared = source[:prefix_end] + route_rules + source[footer_start:]
    prepared, tile_changes = re.subn(
        r"(?m)^(\s*)tiles\([^\n]+\)(\s*)$",
        rf"\g<1>tiles({args.tile_um:g}.um)\g<2>",
        prepared,
        count=1,
    )
    prepared, thread_changes = re.subn(
        r"(?m)^(\s*)threads\(\d+\)(\s*)$",
        rf"\g<1>threads({args.threads})\g<2>",
        prepared,
        count=1,
    )
    if tile_changes != 1 or thread_changes != 1:
        parser.error(
            f"expected one tiles and one threads statement, got {tile_changes} and {thread_changes}"
        )
    if prepared.count(".output(") != 152 or "###   WELL" in prepared:
        raise RuntimeError("route-only deck contains an unexpected rule set")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(prepared)
    print(f"official_route_rule_block_sha256={sha256(route_rules)}")
    print(f"output_sha256={sha256(prepared)}")
    print("route_output_rule_count=152")
    print("route_sections=" + ",".join(sections))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
