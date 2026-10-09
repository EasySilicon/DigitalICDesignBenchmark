#!/usr/bin/env python3
"""Host-only qualification of T08 frame-transaction stress checks.

Requires an independently passing submission with the inherited FIFO structure.
No corrected RTL is bundled. Temporary variants inject fault subsets into that
submission, including incomplete repairs and a truncated wrap checkpoint.
Unmodified/coalescing-only controls must pass. Compile failure is not detection.
The original submission and all frozen trials are read-only inputs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from evaluator.t08_check import evaluate
from evaluator.t08_mutation_check import classify, compiled

ROOT = Path(__file__).resolve().parent.parent
FAULTS = frozenset({"publication", "rollback", "cancellation"})
VARIANTS = {
    "starter_regression": (FAULTS, (23, 24, 25, 26, 27)),
    "publication_unrepaired": (frozenset({"publication"}), (25,)),
    "rollback_unrepaired": (frozenset({"rollback"}), (23, 24, 26, 27)),
    "cancellation_unrepaired": (frozenset({"cancellation"}), (24, 26)),
    "wrap_checkpoint_truncated": (frozenset({"wrap"}), (26, 27)),
}


def replace(source: str, old: str, new: str, expected: int = 1) -> str:
    if source.count(old) != expected:
        raise ValueError(f"FIFO qualification anchor count != {expected}: {old!r}")
    return source.replace(old, new)


def inject(source: str, faults: frozenset[str]) -> str:
    if not faults <= FAULTS | {"wrap"}:
        raise ValueError("unknown FIFO fault")
    # Coalescing itself is not a defect: the dedicated positive control proves it.
    source = replace(source, "\nwire [WIDTH-1:0] s_axis;", """
// Coalesce frame boundary notifications while the advertised batch is resident.
wire commit_sync_ready = wr_ptr_update_reg == wr_ptr_update_ack_sync2_reg &&
    rd_ptr_conv_reg == wr_ptr_sync_commit_reg;

wire [WIDTH-1:0] s_axis;""")
    source = replace(source,
        "if (wr_ptr_update_reg == wr_ptr_update_ack_sync2_reg) begin",
        "if (commit_sync_ready) begin", 3)
    if "publication" in faults:
        source = replace(source, "wr_ptr_sync_commit_reg <= wr_ptr_commit_reg;",
                         "wr_ptr_sync_commit_reg <= wr_ptr_reg;")
    if "rollback" in faults:
        source = replace(source, "wr_ptr_temp = wr_ptr_commit_reg;",
                         "wr_ptr_temp = wr_ptr_sync_commit_reg;", 2)
    if "cancellation" in faults:
        anchor = "wr_ptr_gray_reg <= bin2gray(wr_ptr_temp);\n                    drop_frame_reg <= 1'b0;\n                    overflow_reg <= 1'b1;"
        source = replace(source, anchor, anchor + "\n                    wr_ptr_update_valid_reg <= 1'b0;")
        source = replace(source, "bad_frame_reg <= 1'b1;\n                    end",
                         "bad_frame_reg <= 1'b1;\n                        wr_ptr_update_valid_reg <= 1'b0;\n                    end")
    if "wrap" in faults:
        source = replace(source, "wr_ptr_temp = wr_ptr_commit_reg;",
                         "wr_ptr_temp = {1'b0, wr_ptr_commit_reg[ADDR_WIDTH-1:0]};", 2)
    return source


def qualify(baseline: Path, output: Path, *, jobs: int = 2) -> dict:
    baseline, output = baseline.resolve(), output.resolve()
    if output == baseline or baseline in output.parents:
        raise ValueError("qualification output must be outside the baseline")
    if not 1 <= jobs <= 3:
        raise ValueError("jobs must be between one and three")
    output.mkdir(parents=True, exist_ok=True)
    original = (baseline / "rtl/axis_async_fifo.v").read_text()
    variants = {name: inject(original, faults) for name, (faults, _) in VARIANTS.items()}
    variants["coalescing_control"] = inject(original, frozenset())
    starter = ROOT / "benchmark/tasks/T08/starter/rtl/axis_async_fifo.v"
    if variants["starter_regression"] != starter.read_text():
        raise ValueError("injected full regression does not exactly match published starter FIFO")
    positive = evaluate(baseline, output / "baseline.json")
    if not compiled(positive) or not positive["full_functional_pass"]:
        raise ValueError("baseline must compile and pass the complete current judge")
    records = {}
    with tempfile.TemporaryDirectory(prefix="t08_frame_qualification_") as temp:
        temporary = Path(temp)
        for name, source in variants.items():
            submission = temporary / name
            shutil.copytree(baseline / "rtl", submission / "rtl")
            (submission / "rtl/axis_async_fifo.v").write_text(source)

        def check(name):
            report = evaluate(temporary / name, output / f"{name}.json")
            if name == "coalescing_control":
                record = {"compiled": compiled(report),
                          "passed": report["full_functional_pass"],
                          "functional_total": report["functional_total"]}
            else:
                record = classify(report, VARIANTS[name][1])
            return name, record

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for future in as_completed([pool.submit(check, name) for name in variants]):
                name, record = future.result()
                records[name] = record
                print(json.dumps({"variant": name, **record}), flush=True)
    control = records.pop("coalescing_control")
    result = {
        "task": "T08", "scope": "host-only frame-transaction checker qualification",
        "spec_revision": positive["spec_revision"], "judge_revision": positive["judge_revision"],
        "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "baseline_passed": True, "baseline_run_count": sum(len(c["runs"]) for c in positive["cases"].values()),
        "baseline_rtl_sha256": {str(p.relative_to(baseline / "rtl")):
            hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((baseline / "rtl").rglob("*")) if p.is_file()},
        "judge_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "evaluator/t08_check.py", ROOT / "evaluator/public/tb_T08.sv",
                      ROOT / "evaluator/fixtures/t11_mac/tb_acceptance.sv")},
        "starter_fifo_sha256": hashlib.sha256(starter.read_bytes()).hexdigest(),
        "coalescing_positive_control": control,
        "variant_count": len(records),
        "detected_count": sum(v["detected"] for v in records.values()),
        "variants": records,
        "passed": control["compiled"] and control["passed"] and all(v["detected"] for v in records.values()),
        "limitations": ["Finite negative controls do not prove detection of all possible RTL faults.",
                       "Localization difficulty still requires timed candidate trials.",
                       "Original submissions, frozen input packages and old scores are unchanged."],
    }
    (output / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    result = qualify(args.baseline, args.output_dir, jobs=args.jobs)
    print(json.dumps({"passed": result["passed"], "detected": result["detected_count"],
                      "variants": result["variant_count"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
