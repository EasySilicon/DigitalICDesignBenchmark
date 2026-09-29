#!/usr/bin/env python3
"""Qualify deterministic T05 RTL mutants against the independent evaluator."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from t05_check import ROOT, run


MUTATIONS = {
    "advance_without_ready": (
        "else if (out_valid && out_ready) begin",
        "else if (out_valid) begin",
    ),
    "fixed_priority": (
        "search_start <= out_id + 1'b1;",
        "search_start <= '0;",
    ),
    "multiple_ready": (
        "in_ready = selected & {N{out_ready}};",
        "in_ready = {N{out_ready}};",
    ),
    "no_hold": (
        "locked <= 1'b1;",
        "locked <= 1'b0;",
    ),
    "no_pointer_reset": (
        "search_start <= '0;",
        "search_start <= search_start;",
    ),
    "only_channel_zero": (
        "out_valid = locked || (|in_valid);",
        "out_valid = locked || grant[0];",
    ),
    "skip_pointer": (
        "search_start <= out_id + 1'b1;",
        "search_start <= out_id + 2'b10;",
    ),
    "truncate_data": (
        "out_data |= in_data[i] & {WIDTH{selected[i]}};",
        "out_data |= WIDTH'(8'(in_data[i])) & {WIDTH{selected[i]}};",
    ),
    "wrong_lane": (
        "out_data |= in_data[i] & {WIDTH{selected[i]}};",
        "out_data |= in_data[(i+1)%N] & {WIDTH{selected[i]}};",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    reference = (ROOT / "reference/T05/rtl/round_robin_stream_arbiter.sv").read_text()
    matrix = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T05_mutants_") as temporary:
        base = Path(temporary)
        for name, (needle, replacement) in MUTATIONS.items():
            if reference.count(needle) != 1:
                raise SystemExit(f"mutation anchor is not unique: {name}")
            submission = base / name
            rtl = submission / "rtl"
            rtl.mkdir(parents=True)
            (rtl / "dut.sv").write_text(reference.replace(needle, replacement, 1))
            (rtl / "files.f").write_text("dut.sv\n")
            try:
                result = run(submission, args.seed)
            except Exception as exc:
                matrix[name] = {"eligible": False, "error": str(exc)}
                continue
            failed_groups = [group for group, row in result["groups"].items()
                             if row["cases_passed"] != row["cases_total"]]
            matrix[name] = {"eligible": True, "killed": bool(failed_groups),
                            "failed_groups": failed_groups}
    eligible = [row for row in matrix.values() if row["eligible"]]
    summary = {"task_id": "T05", "seed": args.seed, "mutants": matrix,
               "eligible": len(eligible),
               "killed": sum(row["killed"] for row in eligible)}
    print(json.dumps(summary, indent=2))
    return 0 if eligible and all(row["killed"] for row in eligible) else 1


if __name__ == "__main__":
    raise SystemExit(main())
