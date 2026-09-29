#!/usr/bin/env python3
"""Qualify deterministic synthesizable T01 fault variants."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from t01_check import ROOT, run


ASSIGNMENT = "parallel_out <= {parallel_out[6:0], serial_in};"
MUTATIONS = {
    "reverse_shift": (ASSIGNMENT,
                      "parallel_out <= {serial_in, parallel_out[7:1]};"),
    "falling_edge": ("always_ff @(posedge clock)",
                     "always_ff @(negedge clock)"),
    "clear_after_a5": (ASSIGNMENT,
                       "parallel_out <= (parallel_out == 8'ha5) ? 8'h00 : "
                       "{parallel_out[6:0], serial_in};"),
    "drop_old_bits": (ASSIGNMENT,
                      "parallel_out <= {1'b0, parallel_out[5:0], serial_in};"),
    "invert_input": (ASSIGNMENT,
                     "parallel_out <= {parallel_out[6:0], ~serial_in};"),
    "ignore_zero": (ASSIGNMENT,
                    "if (serial_in) parallel_out <= {parallel_out[6:0], serial_in};"),
    "duplicate_new_bit": (ASSIGNMENT,
                          "parallel_out <= {parallel_out[5:0], serial_in, serial_in};"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    reference = (ROOT / "reference/T01/rtl/serial_in_parallel_out_8bit.sv").read_text()
    variants = dict(MUTATIONS)
    body_start = reference.index("  always_ff")
    body_end = reference.index("endmodule", body_start)
    variants["combinational_follow"] = (
        reference[body_start:body_end],
        "  always_comb parallel_out = {7'b0, serial_in};\n",
    )
    matrix = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T01_mutants_") as temporary:
        root = Path(temporary)
        for name, (needle, replacement) in variants.items():
            if reference.count(needle) != 1:
                raise SystemExit(f"mutation anchor is not unique: {name}")
            submission = root / name
            rtl = submission / "rtl"
            rtl.mkdir(parents=True)
            (rtl / "dut.sv").write_text(reference.replace(needle, replacement, 1))
            (rtl / "files.f").write_text("dut.sv\n")
            try:
                result = run(submission, args.seed)
            except Exception as exc:
                matrix[name] = {"eligible": False, "error": str(exc)}
                continue
            failed = [group for group, row in result["groups"].items()
                      if row["cases_passed"] != row["cases_total"]]
            matrix[name] = {"eligible": True, "killed": bool(failed),
                            "failed_groups": failed}
    eligible = [row for row in matrix.values() if row["eligible"]]
    summary = {"task_id": "T01", "seed": args.seed, "mutants": matrix,
               "eligible": len(eligible),
               "killed": sum(row["killed"] for row in eligible)}
    print(json.dumps(summary, indent=2))
    return 0 if len(eligible) == len(variants) and all(row["killed"] for row in eligible) else 1


if __name__ == "__main__":
    raise SystemExit(main())
