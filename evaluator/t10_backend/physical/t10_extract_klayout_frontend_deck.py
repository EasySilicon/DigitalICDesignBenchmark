#!/usr/bin/env python3
"""Extract unchanged WELL-through-V0 rules from the locked ASAP7 deck."""

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
    parser.add_argument("--tile-um", type=float, default=50.0)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"missing input: {args.input}")
    if args.threads < 1 or args.tile_um <= 0:
        parser.error("--threads and --tile-um must be positive")

    source = args.input.read_text()
    drc_marker = source.index("# DRC section")
    prefix_end = source.index("\n", drc_marker) + 1
    frontend_start = source.index("#  construction layers", prefix_end)
    frontend_end = source.index("###   M1", frontend_start)
    footer_start = source.index("</text>", frontend_end)
    frontend_rules = source[frontend_start:frontend_end].rstrip() + "\n"

    if frontend_rules.count(".output(") != 114:
        parser.error(
            "locked front-end block changed: expected 114 output rules, "
            f"found {frontend_rules.count('.output(')}"
        )
    sections = re.findall(r"(?m)^###\s+([^\r\n]+?)\s*$", frontend_rules)
    expected_sections = [
        "WELL", "FIN", "GATE", "ACTIVE", "GCUT",
        "NSELECT/PSELECT  LVT/SLVT/SRAMVT", "SDT", "LISD", "LIG", "V0",
    ]
    if sections != expected_sections:
        parser.error(f"unexpected front-end section order: {sections}")

    prepared = source[:prefix_end] + frontend_rules + source[footer_start:]
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
    if prepared.count(".output(") != 114 or "###   M1" in prepared:
        raise RuntimeError("front-end-only deck contains an unexpected rule set")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(prepared)
    print(f"official_frontend_rule_block_sha256={sha256(frontend_rules)}")
    print(f"output_sha256={sha256(prepared)}")
    print("frontend_output_rule_count=114")
    print("frontend_sections=" + ",".join(sections))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
