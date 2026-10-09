#!/usr/bin/env python3
"""Qualify deterministic T03 RTL mutants against the independent evaluator."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from t03_check import ROOT, run


MUTATIONS = {
    "count_write_wrong": (
        "12'h008: if (|PSTRB) count_next = merge_bytes(count_reg, PWDATA, PSTRB);",
        "12'h008: if (|PSTRB) count_next = merge_bytes(count_reg, PWDATA, PSTRB) - 1'b1;",
    ),
    "ctrl_reserved_bits": (
        "ctrl_next = merge_bytes(ctrl, PWDATA, PSTRB) & 32'h7;",
        "ctrl_next = merge_bytes(ctrl, PWDATA, PSTRB);",
    ),
    "ignore_load_pstrb": (
        "12'h004: load_next = merge_bytes(load_reg, PWDATA, PSTRB);",
        "12'h004: load_next = PWDATA;",
    ),
    "invalid_success": (
        "assign PSLVERR = access && !address_ok;",
        "assign PSLVERR = 1'b0;",
    ),
    "irq_ungated": (
        "assign irq = pending && ctrl[2];",
        "assign irq = pending;",
    ),
    "setup_early": (
        "assign access = PSEL && PENABLE;",
        "assign access = PSEL;",
    ),
    "status_strobe_ignored": (
        "if (PSTRB[0] && PWDATA[0]) pending_next = 1'b0;",
        "if (PWDATA[0]) pending_next = 1'b0;",
    ),
    "status_zero_clears": (
        "if (PSTRB[0] && PWDATA[0]) pending_next = 1'b0;",
        "if (PSTRB[0] && !PWDATA[0]) pending_next = 1'b0;",
    ),
    "terminal_early": (
        "if (count_reg != 0) count_next = count_reg - 1'b1;",
        "if (count_reg > 1) count_next = count_reg - 1'b1;",
    ),
    "zero_strobe_stalls": (
        "12'h008: if (|PSTRB) count_next = merge_bytes(count_reg, PWDATA, PSTRB);",
        "12'h008: count_next = merge_bytes(count_reg, PWDATA, PSTRB);",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    reference = (ROOT / "reference/T03/rtl/apb4_timer.sv").read_text()
    matrix = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T03_mutants_") as temporary:
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
    summary = {"task_id": "T03", "seed": args.seed, "mutants": matrix,
               "eligible": len(eligible),
               "killed": sum(row["killed"] for row in eligible)}
    print(json.dumps(summary, indent=2))
    return 0 if eligible and all(row["killed"] for row in eligible) else 1


if __name__ == "__main__":
    raise SystemExit(main())
