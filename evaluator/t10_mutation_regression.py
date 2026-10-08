#!/usr/bin/env python3
"""Qualify independent T10 streaming faults against the hidden port checker."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from runner_t10_stream import run

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "reference/T10/rtl/npu_systolic_matmul_16x16.sv"


@dataclass(frozen=True)
class Mutation:
    name: str
    requirement: str
    original: str
    replacement: str
    alternatives: tuple[tuple[str, str], ...] = ()


MUTATIONS = (
    Mutation("boundary_bubble", "continuous block initiation",
             "assign in_ready = active || (used_slots < 5'(SLOT_COUNT));",
             "logic boundary_pause;\n"
             "    always_ff @(posedge clk or negedge rst_n)\n"
             "        if (!rst_n) boundary_pause <= 1'b0;\n"
             "        else boundary_pause <= input_last;\n"
             "    assign in_ready = active || "
             "((used_slots < 5'(SLOT_COUNT)) && !boundary_pause);",
             (("assign in_ready = active || (used_slots < 5'(SLOT_COUNT-1));",
               "logic boundary_pause;\n"
               "    always_ff @(posedge clk or negedge rst_n)\n"
               "        if (!rst_n) boundary_pause <= 1'b0;\n"
               "        else boundary_pause <= input_last;\n"
               "    assign in_ready = active || "
               "((used_slots < 5'(SLOT_COUNT-1)) && !boundary_pause);"),)),
    Mutation("fp4_three_rows", "steady four-row output",
             "rows_per_cycle = 3'(16 / int'(mode_width(slot_mode[read_slot])));",
             "rows_per_cycle = (slot_mode[read_slot]==4'd6 || "
             "slot_mode[read_slot]==4'd9) ? 3'd3 : "
             "3'(16 / int'(mode_width(slot_mode[read_slot])));",
             (("6, 9: rows_per_cycle = 3'd4;",
               "6, 9: rows_per_cycle = 3'd3;"),)),
    Mutation("wrong_block_id", "block identity",
             "out_block_id[s*16 +: 16] = slot_id[read_slot];",
             "out_block_id[s*16 +: 16] = slot_id[0];",
             (("source_block_id[s*16 +: 16] = slot_id[read_slot];",
               "source_block_id[s*16 +: 16] = slot_id[0];"),)),
    Mutation("wrong_row_index", "row ordering",
             "out_row[s*4 +: 4] = 4'(int'(output_row)+s);",
             "out_row[s*4 +: 4] = 4'(int'(output_row)+s+1);",
             (("source_row[s*4 +: 4] = 4'(int'(output_row)+s);",
               "source_row[s*4 +: 4] = 4'(int'(output_row)+s+1);"),)),
    Mutation("truncate_a_bus", "complete A 1024-bit input",
             "assign a_edge_data[r] = a_data[r*64 +: 64];",
             "assign a_edge_data[r] = {32'b0,a_data[r*64 +: 32]};",
             (("a_edge_data[r] <= a_data[r*64 +: 64];",
               "a_edge_data[r] <= {32'b0,a_data[r*64 +: 32]};"),
              ("a_edge_data[r] <= ingress_a_data[r*64 +: 64];",
               "a_edge_data[r] <= {32'b0,ingress_a_data[r*64 +: 32]};"))),
    Mutation("rotate_b_columns", "B column packing",
             "assign b_edge_data[c] = b_data[c*64 +: 64];",
             "assign b_edge_data[c] = b_data[((c+1)%16)*64 +: 64];",
             (("b_edge_data[c] <= b_data[c*64 +: 64];",
               "b_edge_data[c] <= b_data[((c+1)%16)*64 +: 64];"),
              ("b_edge_data[c] <= ingress_b_data[c*64 +: 64];",
               "b_edge_data[c] <= ingress_b_data[((c+1)%16)*64 +: 64];"))),
    Mutation("b_scale_from_a", "independent A/B MX scales",
             "input_bs[c*16 +: 16]};",
             "input_as[c*16 +: 16]};",
             (("in_start ? b_scale[c*16 +: 16] :",
               "in_start ? a_scale[c*16 +: 16] :"),
              ("b_edge_scale[c] <= b_scale[c*16 +: 16];",
               "b_edge_scale[c] <= a_scale[c*16 +: 16];"),
              ("b_edge_scale[c] <= ingress_b_scale[c*16 +: 16];",
               "b_edge_scale[c] <= ingress_a_scale[c*16 +: 16];"))),
    Mutation("late_scale_group", "MX 32-element scale boundary",
             "assign high_scale_group = input_beat >= (width_now >> 1);",
             "assign high_scale_group = input_beat > (width_now >> 1);",
             (("high_scale_group = !in_start && beat_q[1];",
               "high_scale_group = !in_start && beat_q[1] && beat_q[0];"),)),
    Mutation("fp4_wrong_sign", "FP4 E2M1 sign bit",
             "value.sign=raw[3]; end",
             "value.sign=raw[2]; end",
             (("value.sign = raw[3];", "value.sign = raw[2];"),)),
    Mutation("e4m3_wrong_nan", "FP8 E4M3 NaN encoding",
             "exponent_field==highest_exponent && fraction==10'd7)",
             "exponent_field==highest_exponent && fraction==10'd6)",
             (("value.nan_value = raw[6:3] == 4'hf && raw[2:0] == 3'h7;",
               "value.nan_value = raw[6:3] == 4'hf && raw[2:0] == 3'h6;"),)),
    Mutation("unsigned_int8", "signed INT8 multiplication",
             "product8_p11_reg[ilane] <= a8_hi * b8_hi;",
             "product8_p11_reg[ilane] <= $unsigned(a8_hi) * $unsigned(b8_hi);",
             (("product8_reg[ilane] <= a8 * b8;",
               "product8_reg[ilane] <= $unsigned(a8) * $unsigned(b8);"),)),
    Mutation("reset_leaks_results", "reset discards in-flight blocks",
             "complete[slot] <= 1'b0;",
             "complete[slot] <= 1'b1;"),
    Mutation("broken_a_forward", "horizontal PE forwarding",
             "a_out <= a_in;",
             "a_out <= b_in;",
             (("a_out_n <= ~a_in;",
               "a_out_n <= ~b_in;"),)),
    Mutation("metadata_each_beat", "first-beat-only metadata",
             "assign input_mode = in_start ? mode : mode_q;",
             "assign input_mode = mode;"),
)


def materialize(mutation: Mutation, source: str, work_root: Path,
                reference_name: str) -> Path:
    matches = [(original, replacement)
               for original, replacement in
               ((mutation.original, mutation.replacement), *mutation.alternatives)
               if source.count(original) == 1]
    if len(matches) != 1:
        raise ValueError(f"{mutation.name}: expected one unique source anchor, "
                         f"found {len(matches)}")
    original, replacement = matches[0]
    destination = work_root / "mutants" / f"T10_{mutation.name}" / "rtl"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / reference_name).write_text(
        source.replace(original, replacement, 1))
    (destination / "files.f").write_text(reference_name + "\n")
    return destination.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=[m.name for m in MUTATIONS])
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--skip-qualified", action="store_true")
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument("--work-root", type=Path, default=ROOT)
    args = parser.parse_args()
    source = args.reference.read_text()
    selected = [m for m in MUTATIONS if args.only in (None, m.name)]
    results = []
    for mutation in selected:
        submission = materialize(mutation, source, args.work_root,
                                 args.reference.name)
        artifact = args.work_root / "qualification" / "T10_mutation_logs" / mutation.name
        record_file = artifact / "qualification.json"
        record = {"name": mutation.name, "requirement": mutation.requirement,
                  "reference_sha256": hashlib.sha256(source.encode()).hexdigest()}
        if not args.generate_only:
            if args.skip_qualified and record_file.is_file():
                cached = json.loads(record_file.read_text())
                if cached.get("reference_sha256") == record["reference_sha256"] and \
                        cached.get("seed") == args.seed:
                    results.append(cached)
                    print(f"{mutation.name}: CACHED", flush=True)
                    continue
            reset_probe_included = mutation.name == "reset_leaks_results"
            result = run(submission, args.seed, artifact,
                         run_reset_probe=reset_probe_included)
            groups = result.get("groups", {})
            wrong_cases = sum(group["cases_total"]-group["cases_passed"]
                              for group in groups.values())
            compilable = result.get("phase") not in ("compile-failed", "infrastructure")
            caught = compilable and (wrong_cases > 0 or
                                     result.get("phase") == "simulation-failed" or
                                     not result.get("structure", {}).get("passed", False))
            record.update({"compilable": compilable, "caught": caught,
                           "wrong_cases": wrong_cases,
                           "seed": args.seed,
                           "reset_probe_included": reset_probe_included,
                           "phase": result.get("phase"),
                           "structure_passed": result.get("structure", {}).get("passed"),
                           "first_failure": result.get("failures", [None])[0]})
            print(f"{mutation.name}: {'CAUGHT' if caught else 'SURVIVED/INVALID'}",
                  flush=True)
            record_file.parent.mkdir(parents=True, exist_ok=True)
            record_file.write_text(json.dumps(record, indent=2) + "\n")
        results.append(record)
    summary = {"mutants": len(results), "reference_sha256":
               hashlib.sha256(source.encode()).hexdigest(),
               "results": results}
    if not args.generate_only:
        summary["compilable"] = sum(bool(row["compilable"]) for row in results)
        summary["caught"] = sum(bool(row["caught"]) for row in results)
    path = args.work_root / "qualification" / "T10_MUTATIONS.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if args.generate_only or summary["caught"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
