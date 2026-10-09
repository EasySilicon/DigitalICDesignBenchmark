#!/usr/bin/env python3
"""Qualify deterministic T06 RTL mutants against the independent evaluator."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from t06_check import ROOT, run


MUTATIONS = {
    "corrupt_read_data": (
        "RDATA <= PSLVERR ? 0 : PRDATA;",
        "RDATA <= PSLVERR ? 0 : (PRDATA ^ 32'h1);",
    ),
    "drop_b_stall": (
        "if (BVALID && BREADY) BVALID <= 0;",
        "if (BVALID) BVALID <= 0;",
    ),
    "drop_r_stall": (
        "if (RVALID && RREADY) RVALID <= 0;",
        "if (RVALID) RVALID <= 0;",
    ),
    "fixed_write_priority": (
        "prefer_write <= 0;",
        "prefer_write <= 1;",
    ),
    "force_full_strobe": (
        "apb_strb <= w_strb;",
        "apb_strb <= 4'hf;",
    ),
    "high_address_alias": (
        "if (aw_addr[31:16] != 0 || aw_addr[1:0] != 0) begin",
        "if (aw_addr[31:17] != 0 || aw_addr[1:0] != 0) begin",
    ),
    "ignore_wait": (
        "ACCESS: if (PREADY) begin",
        "ACCESS: if (1'b1) begin",
    ),
    "no_b_reset": (
        "BVALID <= 0;\n      BRESP <= '0;",
        "BVALID <= BVALID;\n      BRESP <= '0;",
    ),
    "no_setup": (
        "apb_write <= 1;\n              state <= SETUP;",
        "apb_write <= 1;\n              state <= ACCESS;",
    ),
    "read_error_okay": (
        "RRESP <= PSLVERR ? 2'b10 : 2'b00;",
        "RRESP <= 2'b00;",
    ),
    "read_prot_zero": (
        "apb_prot <= ar_prot;",
        "apb_prot <= '0;",
    ),
    "w_requires_aw": (
        "assign WREADY = !have_w && !write_busy && !BVALID;",
        "assign WREADY = !have_w && !write_busy && !BVALID && (AWVALID || have_aw);",
    ),
    "write_error_okay": (
        "BRESP <= PSLVERR ? 2'b10 : 2'b00;",
        "BRESP <= 2'b00;",
    ),
    "write_prot_zero": (
        "apb_prot <= aw_prot;",
        "apb_prot <= '0;",
    ),
    "zero_strobe_apb": (
        "end else if (w_strb == 0) begin",
        "end else if (1'b0) begin",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    reference = (ROOT / "reference/T06/rtl/axi4lite_to_apb4_bridge.sv").read_text()
    matrix = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T06_mutants_") as temporary:
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
    summary = {"task_id": "T06", "seed": args.seed, "mutants": matrix,
               "eligible": len(eligible),
               "killed": sum(row["killed"] for row in eligible)}
    print(json.dumps(summary, indent=2))
    return 0 if eligible and all(row["killed"] for row in eligible) else 1


if __name__ == "__main__":
    raise SystemExit(main())
