#!/usr/bin/env python3
"""Extract selected, unchanged routing sections from the locked ASAP7 deck."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


EXPECTED_SECTIONS = [
    "M1", "M2", "M3", "V1", "V2", "V3", "M4", "M5", "V4", "V5",
    "M6", "M7", "V6", "V7", "M8", "M9", "V8", "V9",
]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy selected complete M1-M9/V1-V9 sections verbatim from the "
            "locked ASAP7 DRC deck. Only execution parameters may change."
        )
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("sections", nargs="+", choices=EXPECTED_SECTIONS)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--tile-um", type=float, default=100.0)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"missing input: {args.input}")
    if args.threads < 1 or args.tile_um <= 0:
        parser.error("--threads and --tile-um must be positive")
    if len(set(args.sections)) != len(args.sections):
        parser.error("sections must not be repeated")

    source_bytes = args.input.read_bytes()
    source = source_bytes.decode("utf-8")
    newline = "\r\n" if "\r\n" in source else "\n"
    drc_marker = source.index("# DRC section")
    prefix_end = source.index("\n", drc_marker) + 1
    route_start = source.index("###   M1", prefix_end)
    route_end = source.index("#   ONGRID", route_start)
    footer_start = source.index("</text>", route_end)
    route_rules = source[route_start:route_end]
    locked_route_rules = route_rules.rstrip("\r\n") + newline

    header_matches = list(
        re.finditer(r"(?m)^###\s+(M[1-9]|V[1-9])\s*$", route_rules)
    )
    section_names = [match.group(1) for match in header_matches]
    if section_names != EXPECTED_SECTIONS:
        parser.error(f"unexpected route section order: {section_names}")
    if route_rules.count(".output(") != 152:
        parser.error(
            "locked route block changed: expected 152 output rules, found "
            f"{route_rules.count('.output(')}"
        )

    blocks: dict[str, str] = {}
    for index, match in enumerate(header_matches):
        end = (
            header_matches[index + 1].start()
            if index + 1 < len(header_matches)
            else len(route_rules)
        )
        blocks[match.group(1)] = route_rules[match.start():end]

    selected = [name for name in EXPECTED_SECTIONS if name in args.sections]
    selected_rules = (
        "".join(blocks[name] for name in selected).rstrip("\r\n") + newline
    )
    expected_rule_count = sum(blocks[name].count(".output(") for name in selected)
    prepared = source[:prefix_end] + selected_rules + source[footer_start:]
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
            "expected one tiles and one threads statement, got "
            f"{tile_changes} and {thread_changes}"
        )
    if prepared.count(".output(") != expected_rule_count:
        raise RuntimeError("section deck contains an unexpected rule count")
    output_sections = re.findall(
        r"(?m)^###\s+(M[1-9]|V[1-9])\s*$", prepared
    )
    if output_sections != selected:
        raise RuntimeError(f"section deck contains unexpected sections: {output_sections}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(prepared)
    print(f"official_input_sha256={sha256_bytes(source_bytes)}")
    print(f"official_route_rule_block_sha256={sha256(locked_route_rules)}")
    print(
        "official_route_rule_block_normalized_sha256="
        + sha256(locked_route_rules.replace("\r\n", "\n"))
    )
    print(f"selected_rule_block_sha256={sha256(selected_rules)}")
    print(f"output_sha256={sha256(prepared)}")
    print(f"route_output_rule_count={expected_rule_count}")
    print("route_sections=" + ",".join(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
