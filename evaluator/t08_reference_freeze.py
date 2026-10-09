#!/usr/bin/env python3
"""Freeze a private T08 reference bundle only after fresh functional and PPA gates.

This creates an author-owned evidence artifact outside the public repository.
It never changes candidate submissions, task inputs or historical scores.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from ppa_aggregate import aggregate, expected_result_dir, source_hash
from public_check import sources_from_filelist

ROOT = Path(__file__).resolve().parent


def freeze_gate(functional: dict, stress: dict, ppa: dict) -> None:
    if functional.get("full_functional_pass") is not True or functional.get("functional_total") != 50:
        raise ValueError("reference does not pass complete functional /50")
    cases = functional.get("cases", {})
    if len(cases) != 37 or any(len(case.get("runs", [])) != 3 or
                             any(run.get("passed") is not True for run in case["runs"])
                             for case in cases.values()):
        raise ValueError("reference lacks 111 passing functional runs")
    if stress.get("full_pass") is not True or stress.get("run_count") != 270 or stress.get("passed_count") != 270:
        raise ValueError("reference lacks 270 passing stress runs")
    if ppa.get("measurement_status") != "three_seed" or ppa.get("routed") is not True:
        raise ValueError("reference lacks three routed/power seeds")
    for name in ("setup_worst_slack_ns", "hold_worst_slack_ns", "annotation_fraction",
                 "area_um2", "delay_ns", "energy_per_op_pj"):
        value = ppa.get(name)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"reference {name} is not a finite measurement")
    if any(ppa[name] <= 0 for name in ("area_um2", "delay_ns", "energy_per_op_pj")):
        raise ValueError("reference has a nonpositive area/delay/energy measurement")
    if ppa.get("setup_worst_slack_ns", -1) < 0 or ppa.get("hold_worst_slack_ns", -1) < 0 or \
            ppa.get("drc_violations") != 0 or ppa.get("annotation_fraction", 0) < 0.95:
        raise ValueError("reference does not meet 1 GHz timing/hold/DRC/activity gates")
    clocks = {clock: 1000 for clock in ("logic_clk", "tx_clk", "rx_clk")}
    if ppa.get("parameter_set", {}).get("clock_periods_ps") != clocks:
        raise ValueError("reference clock target differs from uniform 1 GHz")
    if [entry["layout_seed"] for entry in ppa.get("per_seed", [])] != [11, 29, 47]:
        raise ValueError("reference layout seeds differ from 11/29/47")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def freeze(submission: Path, aggregate_file: Path, destination: Path) -> dict:
    submission, destination = submission.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError("freeze destination already exists; never overwrite a frozen reference")
    if destination.is_relative_to(ROOT.parent) or destination.is_relative_to(submission):
        raise ValueError("reference must stay outside public repository and candidate source")
    before = source_hash(submission)
    original = json.loads(aggregate_file.read_text())
    pairs = [(Path(row["route_record"]), Path(row["power_record"])) for row in original["per_seed"]]
    ppa = aggregate("T08", submission, pairs)
    if ppa != original:
        raise ValueError("aggregate or source changed since qualification")
    # Fresh replay binds functional evidence to precisely the physically measured
    # source. Write logs beside, not into, the source or final frozen bundle.
    checks = destination.parent / (destination.name + "_final_checks")
    checks.mkdir(parents=True, exist_ok=False)
    for module, output in (("evaluator.t08_check", "functional.json"),
                           ("evaluator.t08_stress_check", "stress.json")):
        with (checks / (output + ".runner.log")).open("w") as stream:
            subprocess.run([sys.executable, "-m", module, str(submission),
                            "--output", str(checks / output)], cwd=ROOT.parent,
                           stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1800)
    functional = json.loads((checks / "functional.json").read_text())
    stress = json.loads((checks / "stress.json").read_text())
    freeze_gate(functional, stress, ppa)
    if before != source_hash(submission) or before != ppa["source_sha256"]:
        raise ValueError("reference source changed during final checks")
    sram = ppa["parameter_set"].get("sram_contract")
    mapped = None
    if sram:
        from t11_sram import validated_mapping
        first_route = json.loads(pairs[0][0].read_text())
        mapped = Path(first_route["mapping_receipt"]).parent
        validated_mapping(submission, mapped)
        for module, name in (("evaluator.t08_check", "mapped_functional.json"),
                             ("evaluator.t08_stress_check", "mapped_stress.json")):
            with (checks / (name + ".runner.log")).open("w") as stream:
                subprocess.run([sys.executable, "-m", module, str(mapped),
                                "--output", str(checks / name)], cwd=ROOT.parent,
                               stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1800)
        freeze_gate(json.loads((checks / "mapped_functional.json").read_text()),
                    json.loads((checks / "mapped_stress.json").read_text()), ppa)
        validated_mapping(submission, mapped)
    if before != source_hash(submission):
        raise ValueError("reference source changed during mapped final checks")
    destination.mkdir(parents=True)
    (destination / "rtl").mkdir()
    shutil.copy2(submission / "rtl/files.f", destination / "rtl/files.f")
    for path in sources_from_filelist(submission):
        target = destination / path.relative_to(submission)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    shutil.copytree(checks, destination / "qualification")
    if mapped:
        shutil.copytree(mapped, destination / "mapped_reference")
        from t11_sram import VENDOR
        shutil.copytree(VENDOR, destination / "vendor/lambdapdk_fakeram7")
    # Archive the actual host evaluator/workload used, not just mutable paths.
    shutil.copytree(ROOT, destination / "frozen_evaluator", ignore=shutil.ignore_patterns("__pycache__"))
    oracle = ROOT.parent / "benchmark/tasks/T10/public/matmul_oracle.py"
    if oracle.is_file():
        oracle_target = destination / "benchmark/tasks/T10/public/matmul_oracle.py"
        oracle_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(oracle, oracle_target)
    if (ROOT.parent / "env/asap7_seq_sim.v").is_file():
        shutil.copy2(ROOT.parent / "env/asap7_seq_sim.v", destination / "asap7_seq_sim.v")
    for row in ppa["per_seed"]:
        route_file, power_file = Path(row["route_record"]), Path(row["power_record"])
        route = json.loads(route_file.read_text())
        results = expected_result_dir(route["report"])
        seed_dir = destination / f"seed{row['layout_seed']}"
        seed_dir.mkdir()
        for name in ("6_final.v", "6_final.odb", "6_final.spef", "6_final.sdc"):
            shutil.copy2(results / name, seed_dir / name)
        for source, name in ((route_file, "route.json"), (power_file, "power.json"),
                             (Path(route["report"]), "6_finish.rpt"),
                             (Path(route["report"]).with_name("5_route_drc.rpt"), "5_route_drc.rpt"),
                             (power_file.parent / "power.log", "power.log"),
                             (power_file.parent / "simulation.log", "simulation.log"),
                             (power_file.parent / "power.tcl", "power.tcl")):
            shutil.copy2(source, seed_dir / name)
    evidence = {"task": "T08", "status": "frozen_reference_1ghz",
                "frozen_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "ppa_policy_revision": ppa["parameter_set"].get("ppa_policy_revision", "1.0-uniform-1ghz"), "ppa": ppa,
                "source_sha256": before, "functional_passes": 111, "stress_passes": 270,
                "toolchain": {tool: subprocess.check_output([tool, flag], text=True).strip()
                              for tool, flag in (("yosys", "-V"), ("openroad", "-version"),
                                                 ("verilator", "--version"))},
                "artifact_sha256": {str(path.relative_to(destination)): sha256(path)
                                    for path in sorted(destination.rglob("*")) if path.is_file()}}
    (destination / "freeze.json").write_text(json.dumps(evidence, indent=2) + "\n")
    for path in destination.rglob("*"):
        if path.is_file():
            path.chmod(0o444)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.submission, args.aggregate, args.destination)
    print(json.dumps({"status": result["status"], "destination": str(args.destination)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
