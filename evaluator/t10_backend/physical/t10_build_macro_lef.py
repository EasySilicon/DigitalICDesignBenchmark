#!/usr/bin/env python3
"""Build a T10 macro LEF with real M8 supply pins and clear PG access.

Input LEF comes from OpenROAD ``write_abstract_lef`` without occupied-layer
bloating. ``m8_pg`` lists M8 special-wire rectangles from the final ODB as
``VDD x1 y1 x2 y2`` or ``VSS x1 y1 x2 y2`` in microns. Lower-layer OBS are
conservatively filled; M8/M9 retain the routed geometry with supply-pin
regions removed from the obstructions.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

RECT_RE = re.compile(r"\bRECT\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*;")
LAYER_RE = re.compile(r"(?m)^[ \t]+LAYER (\w+) ;\n")
PIN_RE = re.compile(r"(?ms)^  PIN (VDD|VSS)\n(.*?)^  END \1\n")
OBS_RE = re.compile(r"(?ms)^  OBS\n(.*?)^  END\n")
SIZE_RE = re.compile(r"(?m)^  SIZE ([\d.]+) BY ([\d.]+) ;$")


def nm(value: str) -> int:
    result = round(float(value) * 1000)
    if abs(float(value) * 1000 - result) > 0.0001:
        raise ValueError(f"LEF coordinate is not on a 1 nm grid: {value}")
    return result


def rects(section: str) -> list[tuple[int, int, int, int]]:
    return [tuple(map(nm, match.groups())) for match in RECT_RE.finditer(section)]


def layer_section(text: str, layer: str) -> str:
    matches = list(LAYER_RE.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1) == layer:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[match.end() : end]
    raise ValueError(f"missing {layer} layer")


def difference(
    box: tuple[int, int, int, int],
    pin: tuple[int, int, int, int],
) -> list[tuple[int, int, int, int]]:
    x1, y1, x2, y2 = box
    px1, py1, px2, py2 = pin
    ix1, iy1 = max(x1, px1), max(y1, py1)
    ix2, iy2 = min(x2, px2), min(y2, py2)
    if ix1 >= ix2 or iy1 >= iy2:
        return [box]
    return [
        item
        for item in (
            (x1, y1, ix1, y2),
            (ix2, y1, x2, y2),
            (ix1, y1, ix2, iy1),
            (ix1, iy2, ix2, y2),
        )
        if item[0] < item[2] and item[1] < item[3]
    ]


def format_rect(box: tuple[int, int, int, int], indent: str) -> str:
    def coord(value: int) -> str:
        return f"{value / 1000:.3f}".rstrip("0").rstrip(".") if value else "0"

    return f"{indent}RECT  {' '.join(map(coord, box))} ;\n"


def build(detailed: Path, m8_pg: Path, output: Path) -> dict[str, int]:
    source = detailed.read_text()
    size = SIZE_RE.search(source)
    if size is None:
        raise ValueError("macro SIZE absent")
    width, height = map(nm, size.groups())
    pg: dict[str, list[tuple[int, int, int, int]]] = {"VDD": [], "VSS": []}
    for line in m8_pg.read_text().splitlines():
        fields = line.split()
        if len(fields) != 5 or fields[0] not in pg:
            raise ValueError(f"invalid M8 PG rectangle: {line}")
        box = tuple(map(nm, fields[1:]))
        if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
            raise ValueError(f"PG rectangle outside macro: {line}")
        pg[fields[0]].append(box)
    if not pg["VDD"] or not pg["VSS"]:
        raise ValueError("both VDD and VSS need M8 shapes")

    def add_m8(match: re.Match[str]) -> str:
        name, body = match.groups()
        if "      LAYER M8 ;" in body:
            raise ValueError(f"{name} already has M8 pins")
        marker = "      LAYER M9 ;\n"
        if marker not in body:
            raise ValueError(f"{name} has no M9 supply pins")
        shapes = "      LAYER M8 ;\n" + "".join(
            format_rect(box, "        ") for box in pg[name]
        )
        return f"  PIN {name}\n" + body.replace(marker, shapes + marker, 1) + f"  END {name}\n"

    source, pin_count = PIN_RE.subn(add_m8, source)
    if pin_count != 2:
        raise ValueError(f"expected two PG pins, found {pin_count}")

    pin_boxes = {"M8": [], "M9": []}
    pin_matches = {match.group(1): match.group(2) for match in PIN_RE.finditer(source)}
    for name in ("VDD", "VSS"):
        for layer in pin_boxes:
            pin_boxes[layer].extend(rects(layer_section(pin_matches[name], layer)))
    if not all(pin_boxes.values()):
        raise ValueError("M8/M9 supply shapes missing")

    obs_match = OBS_RE.search(source)
    if obs_match is None:
        raise ValueError("macro OBS absent")
    old_obs = obs_match.group(1)
    new_obs = ""
    for layer in ("RVTN", "RVTP", "M1", "M2", "M3", "M4", "M5", "M6", "M7"):
        if not layer_section(old_obs, layer):
            raise ValueError(f"empty {layer} OBS")
        new_obs += f"    LAYER {layer} ;\n"
        new_obs += format_rect((0, 0, width, height), "     ")

    counts: dict[str, int] = {}
    for layer in ("M8", "M9"):
        originals = rects(layer_section(old_obs, layer))
        if not originals:
            raise ValueError(f"empty {layer} OBS")
        cleaned: list[tuple[int, int, int, int]] = []
        for box in originals:
            pieces = [box]
            for pin in pin_boxes[layer]:
                pieces = [part for piece in pieces for part in difference(piece, pin)]
                if not pieces:
                    break
            cleaned.extend(pieces)
        if any(
            max(box[0], pin[0]) < min(box[2], pin[2])
            and max(box[1], pin[1]) < min(box[3], pin[3])
            for box in cleaned
            for pin in pin_boxes[layer]
        ):
            raise ValueError(f"{layer} OBS still blocks supply pins")
        new_obs += f"    LAYER {layer} ;\n"
        new_obs += "".join(format_rect(box, "     ") for box in cleaned)
        counts[f"{layer.lower()}_obs_rects"] = len(cleaned)

    result = source[: obs_match.start(1)] + new_obs + source[obs_match.end(1) :]
    output.write_text(result)
    counts.update(m8_vdd_shapes=len(pg["VDD"]), m8_vss_shapes=len(pg["VSS"]))
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("detailed_lef", type=Path)
    parser.add_argument("m8_pg_rectangles", type=Path)
    parser.add_argument("output_lef", type=Path)
    args = parser.parse_args()
    print(build(args.detailed_lef, args.m8_pg_rectangles, args.output_lef))


if __name__ == "__main__":
    main()
