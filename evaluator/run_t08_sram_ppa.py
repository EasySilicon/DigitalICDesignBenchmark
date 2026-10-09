#!/usr/bin/env python3
"""Reproducible T08 SRAM PPA qualification; run inside a bounded systemd scope.

No agent/token timeout and no historical score writes. Each stage is logged;
physical misses remain measurements, not silently converted into a freeze.
"""
from __future__ import annotations
import argparse
import datetime
import fcntl
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ppa_aggregate import aggregate, expected_result_dir, source_hash
from t11_sram import contract, prepare, sha256, validated_mapping, MACRO_SIM

ROOT = Path(__file__).resolve().parent


def reusable_route(path: Path, receipt: dict, seed: int) -> dict:
    route = json.loads(path.read_text())
    clocks = {clock: 1000 for clock in ("logic_clk", "tx_clk", "rx_clk")}
    expected = dict(task="T08", exit_code=0, seed=seed, corner="WC", period_ps=1000,
                    utilization=10, density=0.6, clock_periods_ps=clocks,
                    sram_contract=receipt["policy"], source_sha256=receipt["source_sha256"],
                    mapped_netlist_sha256=receipt["mapped_netlist_sha256"],
                    macro_count=receipt["macro_count"], disconnected_macro_inputs=0)
    if any(route.get(key) != value for key, value in expected.items()):
        raise ValueError("cannot resume: completed route provenance differs from qualified RTL/model/parameters")
    final = expected_result_dir(route["report"])
    if not Path(route["report"]).is_file() or not all((final / name).is_file() for name in
            ("6_final.v", "6_final.odb", "6_final.sdc", "6_final.spef")):
        raise ValueError("cannot resume: completed routed artifacts are missing")
    return route


def validated_promotion(submission: Path, evidence: Path) -> tuple[Path, Path]:
    pilot = json.loads(evidence.read_text())
    if pilot.get("measurement_status") != "pilot" or pilot.get("source_sha256") != source_hash(submission) or \
            pilot.get("parameter_set", {}).get("seeds") != [11]:
        raise ValueError("three-seed qualification requires same-source seed11 pilot evidence")
    rows = pilot.get("per_seed", [])
    if len(rows) != 1:
        raise ValueError("single-seed promotion evidence is incomplete")
    pair = Path(rows[0]["route_record"]), Path(rows[0]["power_record"])
    checked = aggregate("T08", submission, [pair], (11,))
    if checked != pilot or checked["setup_worst_slack_ns"] < 0 or checked["hold_worst_slack_ns"] < 0 or \
            checked["drc_violations"] != 0:
        raise ValueError("seed11 did not meet setup/hold/DRC; do not spend on other seeds")
    return pair


def run(submission: Path, output: Path, orfs: Path, prepared: Path | None = None, *, resume: bool = False,
        qualify_from: Path | None = None) -> dict:
    # Optimization is single-seed by default. Other seeds require measured,
    # passing seed11 evidence, not merely an opt-in flag.
    promotion = validated_promotion(submission, qualify_from) if qualify_from else None
    seeds = (11, 29, 47) if promotion else (11,)
    output.mkdir(parents=True, exist_ok=True)
    previous = None
    if resume:
        previous = json.loads((output / "state.json").read_text())
        if previous.get("policy") != contract() or previous.get("submission") != str(submission.resolve()):
            raise ValueError("cannot resume different SRAM model or source directory")
        if previous.get("stage") == "complete" or previous.get("status") in ("frozen", "measured_not_timing_closed"):
            raise ValueError("completed measurement is immutable; use a new run for optimization")
        if previous.get("selected_seeds", [11, 29, 47]) != list(seeds):
            raise ValueError("resume seed set changed; use a fresh qualification directory")
        snapshot = output / ("state.before_resume_" + datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f") + ".json")
        shutil.copy2(output / "state.json", snapshot)
    elif (output / "state.json").exists():
        raise ValueError("run state already exists; use a fresh output directory")
    started = time.monotonic()
    state = {"task": "T08", "policy": contract(), "submission": str(submission.resolve()),
             "started_at": datetime.datetime.now().astimezone().isoformat(),
             "completed_seeds": [], "status": "running", "selected_seeds": list(seeds),
             "qualification_mode": bool(promotion), "promotion_from": str(qualify_from) if qualify_from else None}
    if previous:
        state.update(started_at=previous["started_at"], resumed_at=datetime.datetime.now().astimezone().isoformat(),
                     resume_count=previous.get("resume_count", 0) + 1,
                     prior_elapsed_seconds=previous.get("elapsed_seconds", 0),
                     prior_failure=previous.get("error"), reused_routes=[])
    def update(stage, **fields):
        state.update(stage=stage, elapsed_seconds=round(time.monotonic() - started + state.get("prior_elapsed_seconds", 0), 2),
                     updated_at=datetime.datetime.now().astimezone().isoformat(), **fields)
        pending = output / "state.json.tmp"
        pending.write_text(json.dumps(state, indent=2) + "\n")
        pending.replace(output / "state.json")
        print(json.dumps({k: state[k] for k in ("updated_at", "stage", "status", "completed_seeds")}), flush=True)
    def execute(stage, command):
        update(stage)
        suffix = f".resume{state['resume_count']}" if resume else ""
        with (output / (stage + suffix + ".log")).open("w") as log:
            subprocess.run(command, cwd=ROOT.parent, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
    try:
        # Detect missing transitive Python dependencies before any costly EDA work.
        execute("power_environment_preflight", [sys.executable, str(ROOT / "t08_power_probe.py"), "--help"])
        mapped = prepared.resolve() if prepared else output / "mapped"
        if resume:
            receipt = validated_mapping(submission, mapped)
            if "T11_SRAM_MODEL_PASS" not in (output / "macro_model_selftest.log").read_text():
                raise ValueError("cannot resume without passing macro-model self-test")
            update("reusing_qualified_mapping")
        else:
            model_build = output / "macro_model_build"
            execute("macro_model_compile", ["verilator", "--binary", "--timing", "--assert",
                "-Wno-fatal", "-Wno-SPECIFYIGN", "-j", "4", "--top-module", "tb_t11_sram",
                "--Mdir", str(model_build), str(ROOT / "fixtures/t11_mac/tb_sram.sv"), str(MACRO_SIM)])
            execute("macro_model_selftest", [str(model_build / "Vtb_t11_sram")])
            if "T11_SRAM_MODEL_PASS" not in (output / "macro_model_selftest.log").read_text():
                raise ValueError("macro model did not complete self-test")
            update("memory_mapping")
            mapped = prepared.resolve() if prepared else output / "mapped"
            receipt = json.loads((mapped / "mapping.json").read_text()) if prepared else prepare(submission, mapped)
            for module, name in (("evaluator.t08_check", "mapped_functional"),
                                 ("evaluator.t08_stress_check", "mapped_stress")):
                execute(name, [sys.executable, "-m", module, str(mapped), "--output", str(output / (name + ".json"))])
            functional = json.loads((output / "mapped_functional.json").read_text())
            stress = json.loads((output / "mapped_stress.json").read_text())
            cases = functional.get("cases", {})
            if functional.get("full_functional_pass") is not True or len(cases) != 37 or \
                    any(len(case["runs"]) != 3 or not all(r["passed"] for r in case["runs"]) for case in cases.values()) or \
                    stress.get("full_pass") is not True or stress.get("passed_count") != 270:
                raise ValueError("mapped reference failed functional/stress qualification; not a candidate score")
            (mapped / "evidence").mkdir(exist_ok=True)
            for name in ("mapped_functional.json", "mapped_stress.json"):
                shutil.copy2(output / name, mapped / "evidence" / name)
            qualification = {"mapped_netlist_sha256": sha256(mapped / "rtl/mapped.v"),
                             "contract_sha256": contract()["contract_sha256"],
                             "functional_passes": 111, "stress_passes": 270,
                             "evidence_sha256": {"evidence/" + name: sha256(mapped / "evidence" / name) for name in
                                                 ("mapped_functional.json", "mapped_stress.json")}}
            (mapped / "qualification.json").write_text(json.dumps(qualification, indent=2) + "\n")
            validated_mapping(submission, mapped)
        pairs = []
        for seed in seeds:
            if promotion and seed == 11:
                pairs.append(promotion)
                state["completed_seeds"].append(seed)
                update("seed11_promotion_reused")
                continue
            available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                                 if line.startswith("MemAvailable:")))
            while available < 50 * 1024 * 1024:
                update(f"waiting_for_50GiB_seed{seed}")
                time.sleep(30)
                available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                                     if line.startswith("MemAvailable:")))
            route_dir = output / f"seed{seed}/route"
            power_dir = output / f"seed{seed}" / (f"power_resume{state['resume_count']}" if resume else "power")
            if resume and (route_dir / "result.json").is_file():
                route = reusable_route(route_dir / "result.json", receipt, seed)
                state["reused_routes"].append(seed)
                update(f"seed{seed}_route_reused")
            else:
                execute(f"seed{seed}_route", [sys.executable, str(ROOT / "ppa_probe.py"), "T08", str(submission),
                    "--orfs-root", str(orfs), "--output-dir", str(route_dir),
                    "--seed", str(seed), "--t08-sram-mapping", str(mapped)])
                route = json.loads((route_dir / "result.json").read_text())
            execute(f"seed{seed}_power", [sys.executable, str(ROOT / "t08_power_probe.py"),
                    "--flow-result-dir", str(expected_result_dir(route["report"])),
                    "--output-dir", str(power_dir), "--sram-route", str(route_dir / "result.json")])
            pairs.append((route_dir / "result.json", power_dir / "result.json"))
            state["completed_seeds"].append(seed)
            update(f"seed{seed}_complete")
        ppa = aggregate("T08", submission, pairs, seeds)
        (output / "aggregate.json").write_text(json.dumps(ppa, indent=2) + "\n")
        qualifies = ppa["setup_worst_slack_ns"] >= 0 and ppa["hold_worst_slack_ns"] >= 0 and ppa["drc_violations"] == 0
        if qualifies and promotion:
            execute("reference_freeze", [sys.executable, str(ROOT / "t08_reference_freeze.py"), str(submission),
                    "--aggregate", str(output / "aggregate.json"), "--destination", str(output / "frozen_reference")])
        final_status = ("frozen" if qualifies else "measured_not_timing_closed") if promotion else \
                       ("single_seed_timing_closed" if qualifies else "single_seed_needs_optimization")
        update("complete", status=final_status,
               ppa=ppa, macro_count=receipt["macro_count"])
    except Exception as exc:
        update("failed", status="failed", error=str(exc))
        raise
    return state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("submission", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--orfs-root", type=Path, required=True)
    p.add_argument("--prepared-mapping", type=Path)
    p.add_argument("--resume", action="store_true", help="reuse hash-validated completed mapping/route; preserve failed logs")
    p.add_argument("--qualify-from", type=Path,
                   help="passing same-source seed11 aggregate; reuse seed11 and run 29/47. Default: seed11 only")
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "runner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.submission.resolve(), args.output_dir.resolve(), args.orfs_root.resolve(), args.prepared_mapping,
            resume=args.resume, qualify_from=args.qualify_from)


if __name__ == "__main__":
    main()
