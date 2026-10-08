#!/usr/bin/env python3
"""Audit routed DEF clock nets for forbidden M8/M9 wire segments."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROUTE_LAYER = re.compile(r"\b(?:ROUTED|NEW|FIXED|COVER)\s+(M\d+)\b")


def audit(def_path: Path) -> dict[str, object]:
    section = ""
    entry: list[str] = []
    layers: Counter[str] = Counter()
    clock_nets = 0
    bad_nets: list[str] = []

    with def_path.open() as source:
        for line in source:
            stripped = line.strip()
            if stripped.startswith("NETS ") or stripped.startswith("SPECIALNETS "):
                section = stripped.split()[0]
                continue
            if stripped.startswith("END NETS") or stripped.startswith("END SPECIALNETS"):
                section = ""
                continue
            if not section:
                continue
            if stripped.startswith("- "):
                entry = [stripped]
            elif entry:
                entry.append(stripped)
            if entry and stripped.endswith(";"):
                net = " ".join(entry)
                if "+ USE CLOCK" in net:
                    clock_nets += 1
                    net_layers = ROUTE_LAYER.findall(net)
                    layers.update(net_layers)
                    if any(layer in {"M8", "M9"} for layer in net_layers):
                        bad_nets.append(entry[0].split()[1])
                entry = []

    if clock_nets == 0:
        raise ValueError(f"no clock nets found in {def_path}")
    return {
        "def": str(def_path),
        "clock_nets": clock_nets,
        "clock_segments_by_layer": dict(sorted(layers.items())),
        "forbidden_clock_nets": bad_nets,
        "passed": not bad_nets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("def_path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.def_path)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
