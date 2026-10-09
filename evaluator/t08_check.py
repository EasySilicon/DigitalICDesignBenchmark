#!/usr/bin/env python3
"""Independent experimental T08 functional judge, host only; no official PPA."""
from __future__ import annotations
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from evaluator.public_check import sources_from_filelist

ROOT = Path(__file__).resolve().parent
GROUPS = [
    ("tx_regression", 8, [0, 1, 23, 27]), ("rx_regression", 8, [2, 3, 24, 25, 26]),
    ("frame_tail_repair", 10, [4, 5, 6, 7, 18]),
    ("vlan_admission", 10, [8, 9, 10, 11, 32, 33]),
    ("metadata_headers", 6, [12, 13, 28, 29, 34, 36]),
    ("config_snapshot", 4, [14, 15, 19, 20, 21, 22, 30, 31]),
    ("reset_recovery", 4, [16, 17, 35]),
]
JUDGE_REVISION = "3.1-boundary-crosses"
SEEDS = (20261007, 47, 91)
BOUNDARY_CLOCKS = ((6.25, 0.7), (5.0, 2.3), (3.125, 6.1))
NEW_CASES = {
    28: "fresh enabled bodies 1..18",
    29: "fresh bypass bodies 1..18",
    30: "tagged predecessor then bypass bodies 1..18",
    31: "bypass predecessor then enabled bodies 1..18",
    32: "short-body MAC-error precedence and recovery",
    33: "independent policy oracle over length/header/config crosses",
    34: "queued mixed metadata, terminal stalls and circular reuse",
    35: "coordinated reset with queued metadata then single-byte frames",
    36: "enabled tagged predecessor then enabled short bodies 1..18",
}


def simulation_args(case: int, seed: int) -> list[str]:
    args = [f"+CASE={case}", f"+SEED={seed}"]
    if case in NEW_CASES:
        half, phase = BOUNDARY_CLOCKS[SEEDS.index(seed)]
        args += [f"+LOGIC_HALF_NS={half}", f"+RX_PHASE_NS={phase}"]
    return args

def evaluate(submission: Path, output: Path) -> dict:
    sources = sources_from_filelist(submission)
    records = {}
    with tempfile.TemporaryDirectory(prefix="t08_accept_", dir=str(output.parent)) as temp:
        cmd = ["verilator", "--binary", "--timing", "--assert", "-Wno-fatal",
               "-j", "4", "--top-module", "tb_t08_acceptance", "--Mdir", temp,
               *map(str, sources), str(ROOT/"public/tb_T08.sv"),
               str(ROOT/"fixtures/t11_mac/tb_acceptance.sv")]
        compiled = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output.with_suffix(".compile.log").write_text(compiled.stdout+compiled.stderr)
        for case in sorted({case for _, _, cases in GROUPS for case in cases}):
            runs=[]
            for seed in SEEDS:
                if compiled.returncode:
                    runs.append({"seed":seed,"passed":False,"error":"candidate compile failure"})
                    continue
                try:
                    result = subprocess.run([str(Path(temp)/"Vtb_t08_acceptance"),
                        *simulation_args(case, seed)], capture_output=True,
                        text=True, timeout=30)
                except subprocess.TimeoutExpired as exc:
                    def decoded(value):
                        return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
                    log = decoded(exc.stdout) + decoded(exc.stderr)
                    output.with_name(f"{output.stem}.case{case}.seed{seed}.log").write_text(log)
                    runs.append({"seed":seed,"passed":False,
                                 "error":"candidate simulation timeout","log_tail":log[-2000:]})
                    continue
                log=result.stdout+result.stderr
                output.with_name(f"{output.stem}.case{case}.seed{seed}.log").write_text(log)
                runs.append({"seed":seed,"passed":result.returncode==0 and
                    f"ACCEPT_PASS T08 CASE={case}" in log,"exit_code":result.returncode,
                    "log_tail":log[-2000:]})
            records[case]={"passed":all(r["passed"] for r in runs),"runs":runs}
    groups=[]
    for name,points,cases in GROUPS:
        passed=sum(records[c]["passed"] for c in cases)
        groups.append({"id":name,"possible_points":points,
                       "earned_points":points*passed/len(cases),
                       "passed":passed==len(cases),"cases":cases})
    report={"task":"T08","status":"frozen_task","spec_revision":"3.0-frame-transactions",
            "judge_revision":JUDGE_REVISION,"functional_max":50,
            "functional_total":sum(g["earned_points"] for g in groups),
            "full_functional_pass":all(g["passed"] for g in groups),
            "ppa_status":"candidate_measurement_pending","test_groups":groups,
            "cases":records,"synthesis":"not_evaluated_by_this_functional_judge",
            "boundary_cases":NEW_CASES,
            "boundary_clock_profiles":[{"seed":seed,"logic_half_ns":half,"rx_phase_ns":phase}
                for seed,(half,phase) in zip(SEEDS,BOUNDARY_CLOCKS)]}
    output.write_text(json.dumps(report,indent=2)+"\n")
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    print(json.dumps(evaluate(args.submission.resolve(),args.output.resolve()),indent=2))

if __name__=="__main__":
    main()
