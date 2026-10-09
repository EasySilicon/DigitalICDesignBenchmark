#!/usr/bin/env python3
"""Qualify deterministic T01 RTL mutants against the hidden evaluator."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from t01_check import ROOT, run


MUTATIONS = {
    "positive_comma_only": (
        "is_comma = symbol == COMMA_P || symbol == COMMA_N;",
        "is_comma = symbol == COMMA_P;",
    ),
    "lock_after_two": (
        "if (train_count[phase] == 2) begin",
        "if (train_count[phase] == 1) begin",
    ),
    "force_phase_zero": (
        "acquisition_phase = 4'(phase);",
        "acquisition_phase = 4'd0;",
    ),
    "swap_input_slices": (
        "bit_window[9:0] = previous_bits;\n    bit_window[19:10] = rx_bits;",
        "bit_window[9:0] = rx_bits;\n    bit_window[19:10] = previous_bits;",
    ),
    "consume_invalid_cycles": (
        "if (rx_valid) begin\n        previous_bits <= rx_bits;",
        "if (1'b1) begin\n        previous_bits <= rx_bits;",
    ),
    "marker_at_symbol_15": (
        "if (frame_position == 15) begin",
        "if (frame_position == 14) begin",
    ),
    "never_drop_lock": (
        "end else if (marker_missed_once) begin",
        "end else if (1'b0) begin",
    ),
    "output_unaligned_slice": (
        "symbol_out <= scan_window[locked_phase];",
        "symbol_out <= rx_bits;",
    ),
    "phase_plus_one": (
        "locked_phase <= acquisition_phase;",
        "locked_phase <= acquisition_phase + 1'b1;",
    ),
    "reset_keeps_lock": (
        "previous_valid <= 1'b0;\n      locked <= 1'b0;",
        "previous_valid <= 1'b0;\n      locked <= locked;",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260927)
    args = parser.parse_args()
    reference_path = ROOT / "reference/T01/serdes_rx_comma_aligner.sv"
    reference = reference_path.read_text()
    matrix = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T01_mutants_") as temporary:
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
    summary = {"task_id": "T01", "seed": args.seed, "mutants": matrix,
               "eligible": len(eligible),
               "killed": sum(row["killed"] for row in eligible)}
    print(json.dumps(summary, indent=2))
    return 0 if eligible and all(row["killed"] for row in eligible) else 1


if __name__ == "__main__":
    raise SystemExit(main())
