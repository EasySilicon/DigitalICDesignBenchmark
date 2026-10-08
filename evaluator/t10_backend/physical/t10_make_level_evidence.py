#!/usr/bin/env python3
"""Validate and describe one independently finished T10 hierarchy level."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def artifact(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": digest.hexdigest()}


def one_float(pattern: str, text: str, label: str) -> float:
    matches = re.findall(pattern, text, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"expected one {label}, found {len(matches)}")
    return float(matches[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("level", choices=("pe", "tile", "top"))
    parser.add_argument("seed", type=int, choices=(11, 29, 47))
    parser.add_argument("prefix", type=Path,
                        help="output prefix passed to run_t10_finish_hier_block.sh")
    parser.add_argument("drc_report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    prefix = args.prefix.resolve()
    timing = Path(f"{prefix}_timing.rpt")
    area = Path(f"{prefix}_area.rpt")
    unconstrained = Path(f"{prefix}_unconstrained.rpt")
    clock_audit = prefix.parent / "t10_clock_route_audit.tsv"
    timing_text = timing.read_text()
    setup = one_float(r"^worst slack max\s+([-+]?\d+(?:\.\d+)?)$",
                      timing_text, "setup WNS")
    hold = one_float(r"^worst slack min\s+([-+]?\d+(?:\.\d+)?)$",
                     timing_text, "hold WNS")
    if setup < 0 or hold < 0:
        raise ValueError(f"timing gate failed: setup={setup} ps hold={hold} ps")

    area_um2 = one_float(r"^Design area\s+(\d+(?:\.\d+)?)\s+um\^2\b",
                         area.read_text(), "design area")
    drc_text = args.drc_report.read_text()
    drc_violations = len(re.findall(r"^violation type:", drc_text, re.MULTILINE))
    if drc_violations:
        raise ValueError(f"DRC gate failed: {drc_violations} violations")
    if unconstrained.read_text().strip():
        raise ValueError(f"unconstrained endpoints reported in {unconstrained}")

    clock_text = clock_audit.read_text()
    forbidden = {}
    for layer, count in re.findall(r"^(M[89])\t(\d+)\t", clock_text, re.MULTILINE):
        if int(count):
            forbidden[layer] = int(count)
    if forbidden:
        raise ValueError(f"clock routing uses forbidden upper layers: {forbidden}")

    paths = {
        "odb": Path(f"{prefix}.odb"),
        "sdc": Path(f"{prefix}.sdc"),
        "spef": Path(f"{prefix}.spef"),
        "lef": Path(f"{prefix}.lef"),
        "liberty": Path(f"{prefix}.lib"),
        "timing_report": timing,
        "drc_report": args.drc_report.resolve(),
    }
    evidence = {
        "level": args.level,
        "layout_seed": args.seed,
        "area_um2": area_um2,
        "setup_worst_slack_ps": setup,
        "hold_worst_slack_ps": hold,
        "drc_violations": 0,
        "constraint_coverage": {
            "unconstrained_endpoints": 0,
            "report": artifact(unconstrained),
        },
        "clock_route_audit": artifact(clock_audit),
        "artifacts": {name: artifact(path) for name, path in paths.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({key: evidence[key] for key in (
        "level", "layout_seed", "area_um2", "setup_worst_slack_ps",
        "hold_worst_slack_ps", "drc_violations")}, sort_keys=True))


if __name__ == "__main__":
    main()
