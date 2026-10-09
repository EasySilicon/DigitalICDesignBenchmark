#!/usr/bin/env python3
"""Independent four-configuration functional evaluator for T04."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from public_check import ROOT, sources_from_filelist


PARAMETERS = ((4, 8), (4, 32), (8, 8), (8, 32))
EXPECTED_GROUPS = {f"AC-{index:02d}" for index in range(21, 26)}
GROUP_LINE = re.compile(r"^IC_GROUP (AC-\d+) (\d+) (\d+)$", re.MULTILINE)


def run(submission: Path, seed: int) -> dict:
    sources = sources_from_filelist(submission.resolve())
    aggregate = {group: {"cases_passed": 0, "cases_total": 0,
                         "safety_violation": False}
                 for group in EXPECTED_GROUPS}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T04_hidden_") as temporary:
        for index, (n_inputs, width) in enumerate(PARAMETERS):
            executable = Path(temporary) / f"sim_{index}.vvp"
            compiled = subprocess.run(
                ["iverilog", "-g2012", "-s", "tb_hidden_T04",
                 f"-Ptb_hidden_T04.N={n_inputs}", f"-Ptb_hidden_T04.WIDTH={width}",
                 "-o", str(executable), *map(str, sources),
                 str(ROOT / "t04_hidden_tb.sv")],
                text=True, capture_output=True, timeout=120, check=False,
            )
            if compiled.returncode:
                raise RuntimeError(f"compile failed for N={n_inputs} WIDTH={width}: "
                                   f"{(compiled.stdout + compiled.stderr)[-4000:]}")
            executed = subprocess.run(
                ["vvp", str(executable), f"+SEED={seed}"],
                text=True, capture_output=True, timeout=120, check=False,
            )
            if executed.returncode:
                raise RuntimeError(f"simulation failed for N={n_inputs} WIDTH={width}: "
                                   f"{(executed.stdout + executed.stderr)[-4000:]}")
            rows = GROUP_LINE.findall(executed.stdout)
            if len(rows) != len(EXPECTED_GROUPS) or {row[0] for row in rows} != EXPECTED_GROUPS:
                raise RuntimeError(f"malformed group output for N={n_inputs} WIDTH={width}")
            for group, passed, total in rows:
                passed_i, total_i = int(passed), int(total)
                if total_i <= 0 or passed_i < 0 or passed_i > total_i:
                    raise RuntimeError(f"invalid group count for {group}")
                aggregate[group]["cases_passed"] += passed_i
                aggregate[group]["cases_total"] += total_i
    return {"task_id": "T04", "seed": seed, "groups": dict(sorted(aggregate.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", nargs="?", type=Path)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    if args.reference == (args.submission is not None):
        parser.error("select exactly one of SUBMISSION or --reference")
    submission = args.submission if args.submission is not None else ROOT / "reference/T04"
    try:
        result = run(submission, args.seed)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {"task_id": "T04", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
