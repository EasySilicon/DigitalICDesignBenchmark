#!/usr/bin/env python3
"""Qualify host-only T11 concurrency tests on temporary, compile-valid faults.

No corrected RTL is bundled. Requires the previously qualified inherited FIFO
structure. Original candidate sources, frozen judges and scores are read-only.
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

from evaluator.t11_repair_qualification import inject as coalesce, replace
from evaluator.t11_stress_check import CLOCKS, evaluate

VARIANTS = {
    "tx_full_stuck": (0, (160,)),
    "rx_overflow_resurrection": (2, tuple(CLOCKS)),
    "cross_channel_wire_gate": (1, tuple(CLOCKS)),
    "reset_wire_ghost": (4, tuple(CLOCKS)),
}


def inject(source: str, name: str) -> str:
    if name == "tx_full_stuck":
        source = replace(source, "assign s_axis_tready = (", """// Negative control: first full condition permanently blocks the writer.
reg qualification_stuck = 1'b0;
always @(posedge s_clk) begin
    if (s_rst) qualification_stuck <= 1'b0;
    else if (FRAME_FIFO && !DROP_WHEN_FULL && full) qualification_stuck <= 1'b1;
end
assign s_axis_tready = !qualification_stuck && (""")
    elif name == "rx_overflow_resurrection":
        source = replace(source,
            "if ((full && DROP_WHEN_FULL) || (full_wr && DROP_OVERSIZE_FRAME) || drop_frame_reg) begin",
            "if ((full && DROP_WHEN_FULL) || (full_wr && DROP_OVERSIZE_FRAME)) begin")
    elif name == "cross_channel_wire_gate":
        source = replace(source, "wire [7:0]  tx_fifo_axis_tdata;", """// Negative control: RX activity corrupts independent TX output.
wire qualification_tx_en;
assign gmii_tx_en = qualification_tx_en && !gmii_rx_dv;
wire [7:0]  tx_fifo_axis_tdata;""")
        source = replace(source, ".gmii_tx_en(gmii_tx_en),", ".gmii_tx_en(qualification_tx_en),")
    elif name == "reset_wire_ghost":
        source = replace(source, "wire [7:0]  tx_fifo_axis_tdata;", """// Negative control: leak one stale wire byte after a warm coordinated reset.
wire qualification_tx_en;
reg qualification_ever_tx = 1'b0;
reg [4:0] qualification_release_count = 0;
always @(posedge tx_clk) begin
    if (qualification_tx_en) qualification_ever_tx <= 1'b1;
    if (tx_rst) qualification_release_count <= 0;
    else if (qualification_release_count < 16) qualification_release_count <= qualification_release_count + 1'b1;
end
assign gmii_tx_en = qualification_tx_en ||
    (qualification_ever_tx && !tx_rst && qualification_release_count == 4);
wire [7:0]  tx_fifo_axis_tdata;""")
        source = replace(source, ".gmii_tx_en(gmii_tx_en),", ".gmii_tx_en(qualification_tx_en),")
    else:
        raise ValueError("unknown stress fault")
    return source


def classify(report: dict) -> dict:
    """A compile error or infrastructure timeout is never functional detection."""
    failures = [run for run in report["runs"] if not run["passed"]]
    witnessed = [run for run in failures if run.get("exit_code", 0) != 0 and
                 "%Fatal:" in run.get("log_tail", "") and
                 "testbench watchdog" not in run.get("log_tail", "")]
    return {"compiled": report["compiled"], "run_count": report["run_count"],
            "failed_count": len(failures), "assertion_witness_count": len(witnessed),
            "detected": report["compiled"] and bool(report["runs"]) and
                        len(witnessed) == report["run_count"],
            "matrix": report["matrix"],
            "first_witness": witnessed[0]["log_tail"] if witnessed else None}


def qualify(baseline: Path, output: Path, *, jobs: int = 2) -> dict:
    baseline, output = baseline.resolve(), output.resolve()
    if output == baseline or baseline in output.parents:
        raise ValueError("qualification output must be outside original submission")
    if jobs not in (1, 2, 3):
        raise ValueError("jobs must be one, two or three")
    output.mkdir(parents=True, exist_ok=True)
    fifo = (baseline / "rtl/axis_async_fifo.v").read_text()
    top = (baseline / "rtl/eth_mac_1g_fifo.v").read_text()
    sources = {name: inject(top if name in ("cross_channel_wire_gate", "reset_wire_ghost") else fifo, name)
               for name in VARIANTS}
    sources["coalescing_control"] = coalesce(fifo, frozenset())
    positive = evaluate(baseline, output / "baseline.json")
    if not positive["compiled"] or not positive["full_pass"]:
        raise ValueError("baseline must pass the full concurrency suite before injecting faults")
    records = {}
    with tempfile.TemporaryDirectory(prefix="t11_stress_mutants_", dir=output) as temp:
        temporary = Path(temp)
        for name, source in sources.items():
            submission = temporary / name
            shutil.copytree(baseline / "rtl", submission / "rtl")
            target = "eth_mac_1g_fifo.v" if name in ("cross_channel_wire_gate", "reset_wire_ghost") else "axis_async_fifo.v"
            (submission / "rtl" / target).write_text(source)

        def check(name):
            kwargs = {} if name == "coalescing_control" else {
                "cases": (VARIANTS[name][0],), "clocks": VARIANTS[name][1]}
            report = evaluate(temporary / name, output / f"{name}.json", **kwargs)
            return name, report

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for future in as_completed([pool.submit(check, name) for name in sources]):
                name, report = future.result()
                records[name] = ({"compiled": report["compiled"], "passed": report["full_pass"],
                                  "run_count": report["run_count"]} if name == "coalescing_control"
                                 else classify(report))
                print(json.dumps({"variant": name, **records[name]}), flush=True)
    control = records.pop("coalescing_control")
    result = {
        "task": "T11", "stress_revision": positive["stress_revision"],
        "scope": "author-only dynamic concurrency qualification; no historical score update",
        "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "baseline_passed": True, "baseline_run_count": positive["run_count"],
        "baseline_rtl_sha256": positive["rtl_sha256"], "checker_sha256": positive["checker_sha256"],
        "qualification_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "coalescing_positive_control": control, "variants": records,
        "variant_count": len(records), "detected_count": sum(v["detected"] for v in records.values()),
        "passed": control["compiled"] and control["passed"] and all(v["detected"] for v in records.values()),
        "limitations": ["Finite faults cannot establish exhaustive verification or analog CDC safety.",
                        "Fault anchors apply only to the inherited baseline structure.",
                        "TX-full witness runs at 160 MHz; lower rates need not saturate TX storage.",
                        "Original RTL and scores are unchanged; no corrected reference is published."],
    }
    (output / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    report = qualify(args.baseline, args.output_dir, jobs=args.jobs)
    print(json.dumps({"passed": report["passed"], "detected": report["detected_count"],
                      "variants": report["variant_count"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
