#!/usr/bin/env python3
"""Qualify deterministic T08 RTL mutants against the independent evaluator."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from t08_check import ROOT, run


MUTATIONS = {
    "alias_high_bit": (
        "tags[index] == saved_addr[31:8]",
        "tags[index] == {1'b0,saved_addr[30:8]}",
    ),
    "bad_write_response": (
        "rsp_rdata <= saved_write ? 0 : refill_data",
        "rsp_rdata <= saved_write ? 32'h1 : refill_data",
    ),
    "duplicate_response": (
        "RESP: if(rsp_ready) state <= IDLE;",
        "RESP: state <= RESP;",
    ),
    "evict_clean": (
        "if(valids[index] && dirtys[index]) state <= WB_REQ;",
        "if(valids[index]) state <= WB_REQ;",
    ),
    "hit_full_strobe": (
        "put_word(lines[index],saved_addr[3:2],saved_data,saved_strb)",
        "put_word(lines[index],saved_addr[3:2],saved_data,4'hf)",
    ),
    "miss_full_strobe": (
        "put_word(refill_data,saved_addr[3:2],saved_data,saved_strb)",
        "put_word(refill_data,saved_addr[3:2],saved_data,4'hf)",
    ),
    "no_dirty_evict": (
        "if(valids[index] && dirtys[index]) state <= WB_REQ;",
        "if(1'b0) state <= WB_REQ;",
    ),
    "no_hit_dirty": (
        "commit_dirty <= 1;",
        "commit_dirty <= 0;",
    ),
    "no_miss_dirty": (
        "commit_dirty <= saved_write && saved_strb != 0;",
        "commit_dirty <= 0;",
    ),
    "no_valid_reset": (
        "valids[i] <= 0; dirtys[i] <= 0;",
        "valids[i] <= 1; dirtys[i] <= 0;",
    ),
    "refill_rotated": (
        ": refill_data;\n        commit_way <= 16'b1 << index;",
        ": {refill_data[31:0],refill_data[127:32]};\n        commit_way <= 16'b1 << index;",
    ),
    "reverse_bytes": (
        "data[8*b+:8];",
        "data[8*(3-b)+:8];",
    ),
    "rsp_wait_ready": (
        "assign rsp_valid = state == RESP;",
        "assign rsp_valid = state == RESP && rsp_ready;",
    ),
    "wrong_hit_word": (
        "lines[index][32*int'(saved_addr[3:2])+:32];",
        "lines[index][32*((int'(saved_addr[3:2])+1)%4)+:32];",
    ),
    "wrong_wb_address": (
        "state == WB_REQ ? wb_addr",
        "state == WB_REQ ? {saved_addr[31:4],4'b0}",
    ),
    "wrong_wb_data": (
        "assign mem_req_wdata = wb_data;",
        "assign mem_req_wdata = wb_data ^ 128'h1;",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--only", choices=sorted(MUTATIONS))
    args = parser.parse_args()
    reference = (ROOT / "reference/T08/rtl/ref.sv").read_text()
    matrix = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T08_mutants_") as temporary:
        base = Path(temporary)
        selected = ({args.only: MUTATIONS[args.only]} if args.only else MUTATIONS)
        for name, (needle, replacement) in selected.items():
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
    summary = {"task_id": "T08", "seed": args.seed, "mutants": matrix,
               "eligible": len(eligible),
               "killed": sum(row["killed"] for row in eligible)}
    print(json.dumps(summary, indent=2))
    return 0 if eligible and all(row["killed"] for row in eligible) else 1


if __name__ == "__main__":
    raise SystemExit(main())
