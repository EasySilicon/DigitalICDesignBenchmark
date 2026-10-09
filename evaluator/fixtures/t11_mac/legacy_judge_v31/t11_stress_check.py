#!/usr/bin/env python3
"""Host-only T11 concurrency qualification; separate from frozen scored trials."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import subprocess
import tempfile
from pathlib import Path

from evaluator.public_check import sources_from_filelist

ROOT = Path(__file__).resolve().parent
REVISION = "1.0-concurrency-progress"
CASES = {
    0: "continuous TX full/backpressure/drain/restart and bad-frame rollback",
    1: "sustained full duplex with RX stalls, mixed metadata and corrupt/denied frames",
    2: "overflowed RX frame cannot resurrect after mid-frame space release",
    3: "publication/discard interleavings over twelve external release windows",
    4: "coordinated reset during TX padding/FCS and queued RX metadata; six release orders",
    5: "near-full RX concurrent read/write, asynchronous space return and ring reuse",
}
CLOCKS = {80: 6.25, 100: 5.0, 120: 25/6, 125: 4.0, 160: 3.125}
SEEDS = (20261007, 47, 91)
PHASES = (0.01, 2.3, 7.99)


def evaluate(submission: Path, output: Path, *, cases=tuple(CASES), seeds=SEEDS,
             clocks=tuple(CLOCKS), phases=PHASES) -> dict:
    submission, output = submission.resolve(), output.resolve()
    if output == submission or submission in output.parents:
        raise ValueError("author report must be outside the original submission")
    if not cases or not seeds or not clocks or not phases or not set(cases) <= CASES.keys():
        raise ValueError("select nonempty supported cases and matrix axes")
    if not set(clocks) <= CLOCKS.keys() or any(not 0 <= phase < 8 for phase in phases):
        raise ValueError("clock/phase outside supported profile")
    for axis in (cases, seeds, clocks, phases):
        if len(axis) != len(set(axis)):
            raise ValueError("duplicate matrix entries")
    sources = sources_from_filelist(submission)
    output.parent.mkdir(parents=True, exist_ok=True)
    runs = []
    fixtures = (ROOT / "public/tb_T11.sv", ROOT / "fixtures/t11_mac/tb_stress.sv")
    with tempfile.TemporaryDirectory(prefix="t11_stress_", dir=output.parent) as temp:
        cmd = ["verilator", "--binary", "--timing", "--assert", "-Wno-fatal", "-j", "4",
               "--top-module", "tb_t11_stress", "--Mdir", temp,
               *map(str, sources), *map(str, fixtures)]
        compiled = subprocess.run(cmd, text=True, capture_output=True, timeout=300)
        output.with_suffix(".compile.log").write_text(compiled.stdout + compiled.stderr)
        for case, seed, clock, phase in itertools.product(cases, seeds, clocks, phases):
            record = {"case": case, "seed": seed, "logic_mhz": clock, "rx_phase_ns": phase}
            if compiled.returncode:
                record.update(passed=False, error="RTL/testbench compile failure; not functional detection")
            else:
                args = [str(Path(temp) / "Vtb_t11_stress"), f"+STRESS_CASE={case}", f"+SEED={seed}",
                        f"+LOGIC_HALF_NS={CLOCKS[clock]}", f"+RX_PHASE_NS={phase}"]
                try:
                    result = subprocess.run(args, text=True, capture_output=True, timeout=30)
                    log = result.stdout + result.stderr
                    match = re.search(r"^STRESS_METRICS (\{[^\n]+\})$", log, re.M)
                    record.update(exit_code=result.returncode, passed=result.returncode == 0 and
                                  f"STRESS_PASS T11 CASE={case}" in log and bool(match))
                    if match:
                        record["metrics"] = json.loads(match[1])
                except subprocess.TimeoutExpired as exc:
                    def decoded(value):
                        return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
                    log = decoded(exc.stdout) + decoded(exc.stderr)
                    record.update(passed=False, error="simulation timeout")
                filename = f"{output.stem}.case{case}.seed{seed}.mhz{clock}.phase{phase}.log"
                output.with_name(filename).write_text(log)
                record["log"] = filename
                record["log_tail"] = log[-2500:]
            runs.append(record)
            if (seed, clock, phase) == (seeds[-1], clocks[-1], phases[-1]):
                selected = [run for run in runs if run["case"] == case]
                print(json.dumps({"case": case, "runs": len(selected),
                                  "passed": sum(run["passed"] for run in selected)}), flush=True)
    report = {
        "task": "T11", "scope": "author-side concurrency qualification; no historical score update",
        "stress_revision": REVISION, "compiled": compiled.returncode == 0,
        "full_pass": all(run["passed"] for run in runs), "run_count": len(runs),
        "passed_count": sum(run["passed"] for run in runs), "cases": {case: CASES[case] for case in cases},
        "matrix": {"seeds": list(seeds), "logic_mhz": list(clocks), "rx_phase_ns": list(phases)},
        "rtl_sha256": {str(path.relative_to(submission / "rtl")): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in sources},
        "checker_sha256": {str(path.relative_to(ROOT.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in (*fixtures, Path(__file__))},
        "runs": runs,
        "limitations": [
            "Finite dynamic tests do not prove absence of deadlock or metastability.",
            "External release windows target CDC/publication races; internal ACK coincidences are not measured.",
            "Watchdog/progress budgets are diagnostic simulation guards, not new exact latency requirements.",
            "No single-domain reset, stopped GMII clocks, jumbo traffic or multi-queue arbitration is required.",
            "Preparation and author simulation are excluded from candidate EDA time.",
        ],
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=int, nargs="+", choices=tuple(CASES), default=tuple(CASES))
    parser.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    parser.add_argument("--clocks", type=int, nargs="+", choices=tuple(CLOCKS), default=tuple(CLOCKS))
    parser.add_argument("--rx-phases", type=float, nargs="+", default=PHASES)
    args = parser.parse_args()
    report = evaluate(args.submission, args.output, cases=tuple(args.cases), seeds=tuple(args.seeds),
                      clocks=tuple(args.clocks), phases=tuple(args.rx_phases))
    print(json.dumps({"compiled": report["compiled"], "passed": report["passed_count"],
                      "runs": report["run_count"], "full_pass": report["full_pass"]}))
    return 0 if report["full_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
