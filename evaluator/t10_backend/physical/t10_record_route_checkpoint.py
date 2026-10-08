#!/usr/bin/env python3
"""Write one hash-bound T10 PE detailed-route checkpoint record."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


def artifact(path: Path) -> dict[str, object]:
    path = path.resolve(strict=True)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": digest.hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", type=int, required=True)
    parser.add_argument("--mode", choices=("initial", "restart", "repair"),
                        required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--seed", type=int, choices=(11, 29, 47), required=True)
    parser.add_argument("--drvs", type=int, required=True)
    parser.add_argument("--input-odb", type=Path, required=True)
    parser.add_argument("--output-odb", type=Path, required=True)
    parser.add_argument("--drc-report", type=Path, required=True)
    parser.add_argument("--maze-log", type=Path, required=True)
    parser.add_argument("--openroad-log", type=Path, required=True)
    args = parser.parse_args()
    if args.stage < 0 or not 1 <= args.iterations <= 64 or args.drvs < 0:
        parser.error("stage, iterations, or DRC count is outside its valid range")

    input_record = artifact(args.input_odb)
    output_record = artifact(args.output_odb)
    payload = {
        "schema_version": 1,
        "status": "clean" if args.drvs == 0 else "repair_required",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stage": args.stage,
        "mode": args.mode,
        "iterations": args.iterations,
        "layout_seed": args.seed,
        "drvs": args.drvs,
        "input_odb": input_record["path"],
        "input_sha256": input_record["sha256"],
        "output_odb": output_record["path"],
        "output_sha256": output_record["sha256"],
        "artifacts": {
            "output_odb": output_record,
            "drc_report": artifact(args.drc_report),
            "maze_log": artifact(args.maze_log),
            "openroad_log": artifact(args.openroad_log),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"stage": args.stage, "drvs": args.drvs,
                      "output": str(args.output.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
