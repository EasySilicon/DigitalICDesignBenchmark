#!/usr/bin/env python3
"""Qualify deterministic T02 RTL mutants against the hidden evaluator."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from t02_check import ROOT, run


MUTATIONS = {
    "bad_wrap": (
        "wr_ptr <= (wr_ptr == DEPTH - 1) ? '0 : wr_ptr + 1'b1;",
        "wr_ptr <= (wr_ptr == DEPTH) ? '0 : wr_ptr + 1'b1;",
    ),
    "empty_pop": (
        "if (pop)\n        rd_ptr <= (rd_ptr == DEPTH - 1) ? '0 : rd_ptr + 1'b1;",
        "if (out_ready)\n        rd_ptr <= (rd_ptr == DEPTH - 1) ? '0 : rd_ptr + 1'b1;",
    ),
    "fallthrough": (
        "assign out_valid = count != 0;",
        "assign out_valid = (count != 0) || in_valid;",
    ),
    "narrow_storage": (
        "logic [WIDTH-1:0] storage [0:DEPTH-1];",
        "logic [7:0] storage [0:DEPTH-1];",
    ),
    "no_count_reset": (
        "count <= '0;",
        "count <= count;",
    ),
    "no_full_replace": (
        "assign in_ready = (count != DEPTH) || (out_valid && out_ready);",
        "assign in_ready = (count != DEPTH);",
    ),
    "reverse_order": (
        "assign out_data = storage[rd_ptr];",
        "assign out_data = storage[wr_ptr];",
    ),
    "short_capacity": (
        "assign in_ready = (count != DEPTH) || (out_valid && out_ready);",
        "assign in_ready = (count < DEPTH-1) || (out_valid && out_ready);",
    ),
    "skip_last_write": (
        "storage[wr_ptr] <= in_data;",
        "if (wr_ptr != DEPTH-1) storage[wr_ptr] <= in_data;",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    reference = (ROOT / "reference/T02/rtl/synchronous_fifo.sv").read_text()
    matrix = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T02_mutants_") as temporary:
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
            except Exception as exc:  # compile failures are invalid mutants, not kills
                matrix[name] = {"eligible": False, "error": str(exc)}
                continue
            failed_groups = [group for group, row in result["groups"].items()
                             if row["cases_passed"] != row["cases_total"]]
            matrix[name] = {"eligible": True, "killed": bool(failed_groups),
                            "failed_groups": failed_groups}
    eligible = [row for row in matrix.values() if row["eligible"]]
    summary = {"task_id": "T02", "seed": args.seed, "mutants": matrix,
               "eligible": len(eligible),
               "killed": sum(row["killed"] for row in eligible)}
    print(json.dumps(summary, indent=2))
    return 0 if eligible and all(row["killed"] for row in eligible) else 1


if __name__ == "__main__":
    raise SystemExit(main())
