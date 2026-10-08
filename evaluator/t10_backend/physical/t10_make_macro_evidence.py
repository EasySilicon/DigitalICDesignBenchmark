#!/usr/bin/env python3
"""Validate and describe a routed leaf macro used by the frozen T10 PE."""

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
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def one_float(pattern: str, text: str, label: str) -> float:
    matches = re.findall(pattern, text, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"expected one {label}, found {len(matches)}")
    return float(matches[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=("fp0", "fp1", "fp2", "int", "cpa"))
    parser.add_argument("seed", type=int, choices=(11, 29, 47))
    parser.add_argument("prefix", type=Path)
    parser.add_argument("drc_report", type=Path)
    parser.add_argument("source_rtl", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--lef", type=Path,
                        help="parent-facing LEF; defaults to PREFIX.lef")
    parser.add_argument("--liberty", type=Path,
                        help="parent-facing Liberty; defaults to PREFIX.lib")
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
    forbidden = {
        layer: int(count)
        for layer, count in re.findall(r"^(M[89])\t(\d+)\t", clock_text, re.MULTILINE)
        if int(count)
    }
    if forbidden:
        raise ValueError(f"clock routing uses forbidden upper layers: {forbidden}")

    paths = {
        "odb": Path(f"{prefix}.odb"),
        "sdc": Path(f"{prefix}.sdc"),
        "spef": Path(f"{prefix}.spef"),
        "lef": args.lef.resolve() if args.lef else Path(f"{prefix}.lef"),
        "liberty": (args.liberty.resolve() if args.liberty
                    else Path(f"{prefix}.lib")),
        "timing_report": timing,
        "drc_report": args.drc_report.resolve(),
        "unconstrained_report": unconstrained,
        "clock_route_audit": clock_audit,
    }
    evidence = {
        "component": args.component,
        "layout_seed": args.seed,
        "source_rtl": artifact(args.source_rtl.resolve()),
        "area_um2": area_um2,
        "setup_worst_slack_ps": setup,
        "hold_worst_slack_ps": hold,
        "drc_violations": 0,
        "unconstrained_endpoints": 0,
        "artifacts": {name: artifact(path) for name, path in paths.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({key: evidence[key] for key in (
        "component", "layout_seed", "area_um2", "setup_worst_slack_ps",
        "hold_worst_slack_ps", "drc_violations")}, sort_keys=True))


if __name__ == "__main__":
    main()
