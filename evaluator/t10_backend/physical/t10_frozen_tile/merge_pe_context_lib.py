#!/usr/bin/env python3
"""Merge exact compute input constraints into the complete routed PE ETM.

OpenSTA omits unrelated output arcs when a timing model is written after the
unused PE forwarding cone is false-pathed.  The original ETM and the filtered
ETM come from the same routed ODB/SDC/SPEF checkpoint.  Keep the complete
original interface and replace only setup/hold blocks that the filtered model
regenerated for real compute ingress paths.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Block:
    name: str
    start: int
    end: int
    text: str


def matching_brace(text: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError(f"unterminated block at offset {opening}")


def named_blocks(text: str, keyword: str) -> dict[str, Block]:
    pattern = re.compile(
        rf"(?m)^\s*{re.escape(keyword)}\s*\(\s*\"?([^\"\)]+)\"?\s*\)\s*\{{"
    )
    result: dict[str, Block] = {}
    for match in pattern.finditer(text):
        end = matching_brace(text, text.index("{", match.start(), match.end()))
        name = match.group(1).strip()
        result[name] = Block(name, match.start(), end, text[match.start():end])
    return result


def timing_blocks(pin_text: str) -> dict[str, Block]:
    result: dict[str, Block] = {}
    for match in re.finditer(r"(?m)^\s*timing\s*\(\s*\)\s*\{", pin_text):
        end = matching_brace(pin_text,
                             pin_text.index("{", match.start(), match.end()))
        block_text = pin_text[match.start():end]
        kind = re.search(r"timing_type\s*:\s*([A-Za-z0-9_]+)", block_text)
        if kind and kind.group(1) in {"setup_rising", "hold_rising"}:
            if kind.group(1) in result:
                raise ValueError(f"duplicate {kind.group(1)} timing block")
            result[kind.group(1)] = Block(
                kind.group(1), match.start(), end, block_text
            )
    return result


def replace_constraints(base_pin: str, context_pin: str) -> tuple[str, int]:
    base_timing = timing_blocks(base_pin)
    context_timing = timing_blocks(context_pin)
    replacements: list[tuple[int, int, str]] = []
    for kind in ("setup_rising", "hold_rising"):
        if kind not in context_timing:
            continue
        if kind not in base_timing:
            raise ValueError(f"base pin is missing {kind}")
        old = base_timing[kind]
        replacements.append((old.start, old.end, context_timing[kind].text))
    output = base_pin
    for start, end, replacement in sorted(replacements, reverse=True):
        output = output[:start] + replacement + output[end:]
    return output, len(replacements)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("filtered", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    base = args.base.read_text()
    filtered = args.filtered.read_text()
    base_pins = named_blocks(base, "pin")
    filtered_pins = named_blocks(filtered, "pin")
    replacements: list[tuple[int, int, str]] = []
    replaced_setup_pins: set[str] = set()
    replaced_blocks = 0
    for name, base_pin in base_pins.items():
        if name not in filtered_pins:
            raise ValueError(f"filtered model is missing pin {name}")
        merged_pin, count = replace_constraints(
            base_pin.text, filtered_pins[name].text
        )
        if count:
            if count != 2:
                raise ValueError(f"pin {name} has only one filtered constraint")
            replaced_setup_pins.add(name)
            replaced_blocks += count
            replacements.append((base_pin.start, base_pin.end, merged_pin))

    expected_unfiltered = {f"bt_in[{bit}]" for bit in range(17, 27)}
    base_setup_pins = {
        name for name, block in base_pins.items()
        if "timing_type : setup_rising" in block.text
    }
    if base_setup_pins - replaced_setup_pins != expected_unfiltered:
        raise ValueError(
            "unexpected PE inputs without compute constraints: "
            f"{sorted(base_setup_pins - replaced_setup_pins)}"
        )
    if len(replaced_setup_pins) != 174 or replaced_blocks != 348:
        raise ValueError(
            f"expected 174 setup/hold pin pairs, got "
            f"{len(replaced_setup_pins)} pins/{replaced_blocks} blocks"
        )

    output = base
    for start, end, replacement in sorted(replacements, reverse=True):
        output = output[:start] + replacement + output[end:]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output)
    print(
        "T10_PE_CONTEXT_LIB_MERGE "
        f"compute_pins={len(replaced_setup_pins)} "
        f"retained_dead_forward_only_pins={len(expected_unfiltered)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
