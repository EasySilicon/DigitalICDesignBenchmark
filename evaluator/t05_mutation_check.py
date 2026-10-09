#!/usr/bin/env python3
"""Qualify deterministic T05 RTL mutants against behavioral and CDC checks."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from t05_check import ROOT, run


QUALIFICATION_PARAMETERS = ((8, 8), (32, 16))
FAILURE_GROUP = re.compile(r"^IC_FAILURE (AC-\d+) ", re.MULTILINE)


MUTATIONS = {
    "one_stage_read_pointer": (
        "rd_gray_sync2 <= rd_gray_sync1;",
        "rd_gray_sync2 <= rd_gray;",
    ),
    "one_stage_write_pointer": (
        "wr_gray_sync2 <= wr_gray_sync1;",
        "wr_gray_sync2 <= wr_gray;",
    ),
    "binary_write_pointer_crossing": (
        "assign wr_gray_next = (wr_bin_next >> 1) ^ wr_bin_next;",
        "assign wr_gray_next = wr_bin_next;",
    ),
    "wrong_full_gray_polarity": (
        "assign full_next = wr_gray_next == {\n"
        "    ~rd_gray_sync2[PTR_W-1:PTR_W-2], rd_gray_sync2[PTR_W-3:0]\n"
        "  };",
        "assign full_next = wr_gray_next == {\n"
        "    ~rd_gray_sync2[PTR_W-1], rd_gray_sync2[PTR_W-2:0]\n"
        "  };",
    ),
    "wrong_read_address": (
        "assign rd_data = mem[rd_bin[ADDR_W-1:0]];",
        "assign rd_data = mem[rd_bin[ADDR_W-1:0] + 1'b1];",
    ),
    "overwrite_slot_zero": (
        "mem[wr_bin[ADDR_W-1:0]] <= wr_data;",
        "mem['0] <= wr_data;",
    ),
    "truncate_read_data": (
        "assign rd_data = mem[rd_bin[ADDR_W-1:0]];",
        "assign rd_data = WIDTH'(mem[rd_bin[ADDR_W-1:0]][7:0]);",
    ),
    "advance_read_without_transfer": (
        "assign rd_bin_next  = rd_bin + (rd_valid && rd_ready);",
        "assign rd_bin_next  = rd_bin + rd_ready;",
    ),
    "invert_written_data": (
        "mem[wr_bin[ADDR_W-1:0]] <= wr_data;",
        "mem[wr_bin[ADDR_W-1:0]] <= ~wr_data;",
    ),
    "shift_write_address": (
        "mem[wr_bin[ADDR_W-1:0]] <= wr_data;",
        "mem[wr_bin[ADDR_W-1:0] + 1'b1] <= wr_data;",
    ),
    "unstable_when_blocked": (
        "assign rd_data = mem[rd_bin[ADDR_W-1:0]];",
        "assign rd_data = mem[rd_bin[ADDR_W-1:0] + (!rd_ready)];",
    ),
    "remote_reset_read_sync": (
        "always_ff @(posedge wr_clk or negedge wr_rst_n) begin\n"
        "    if (!wr_rst_n) begin\n"
        "      rd_gray_sync1",
        "always_ff @(posedge wr_clk or negedge rd_rst_n) begin\n"
        "    if (!rd_rst_n) begin\n"
        "      rd_gray_sync1",
    ),
    "remote_reset_write_sync": (
        "always_ff @(posedge rd_clk or negedge rd_rst_n) begin\n"
        "    if (!rd_rst_n) begin\n"
        "      wr_gray_sync1",
        "always_ff @(posedge rd_clk or negedge wr_rst_n) begin\n"
        "    if (!wr_rst_n) begin\n"
        "      wr_gray_sync1",
    ),
}


def synthesize_mutant(source: Path) -> None:
    for width, depth in QUALIFICATION_PARAMETERS:
        script = (f"read_verilog -sv {source}\n"
                  f"chparam -set WIDTH {width} -set DEPTH {depth} asynchronous_fifo\n"
                  "synth -top asynchronous_fifo\ncheck -assert\n")
        result = subprocess.run(["yosys", "-Q", "-T", "-q", "-p", script],
                                text=True, capture_output=True, timeout=180,
                                check=False)
        if result.returncode:
            raise RuntimeError(f"Yosys synthesis failed for WIDTH={width} "
                               f"DEPTH={depth}: {(result.stdout + result.stderr)[-4000:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260928)
    args = parser.parse_args()
    reference = (ROOT / "reference/T05/rtl/asynchronous_fifo.sv").read_text()
    matrix = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T05_mutants_") as temporary:
        base = Path(temporary)
        for name, (needle, replacement) in MUTATIONS.items():
            if reference.count(needle) != 1:
                raise SystemExit(f"mutation anchor is not unique: {name}")
            submission = base / name
            rtl = submission / "rtl"
            rtl.mkdir(parents=True)
            source = rtl / "dut.sv"
            source.write_text(reference.replace(needle, replacement, 1))
            (rtl / "files.f").write_text("dut.sv\n")
            try:
                synthesize_mutant(source)
                # One small and one large configuration cover both pointer
                # widths while keeping deterministic mutation qualification
                # materially cheaper than a full candidate evaluation.
                result = run(submission, args.seed, QUALIFICATION_PARAMETERS)
            except Exception as exc:
                # Some broken FIFOs report an observable protocol failure and
                # then time out while the testbench drains them. That is a
                # valid kill, provided Yosys synthesis already succeeded.
                message = str(exc)
                failed_groups = sorted(set(FAILURE_GROUP.findall(message)))
                if message.startswith("simulation failed") and failed_groups:
                    matrix[name] = {"eligible": True, "killed": True,
                                    "failed_groups": failed_groups,
                                    "terminated_after_failure": True}
                else:
                    matrix[name] = {"eligible": False, "error": message}
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
    return 0 if len(eligible) == len(MUTATIONS) and len(eligible) >= 12 and \
        all(row["killed"] for row in eligible) else 1


if __name__ == "__main__":
    raise SystemExit(main())
