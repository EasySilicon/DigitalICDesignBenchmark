#!/usr/bin/env python3
"""Requalify and freeze T09 only after functional, cycle and three-seed PPA gates.

The existing baseline is not touched on failure. Raw evidence is retained in
the public repository; historical contestant scores are not automatically
regraded when the reference changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__:
    from .ppa_aggregate import aggregate, expected_result_dir, source_hash
    from .ppa_probe import constraint_text, report_fields
    from .t09_timing_check import case_inventory
else:
    from ppa_aggregate import aggregate, expected_result_dir, source_hash
    from ppa_probe import constraint_text, report_fields
    from t09_timing_check import case_inventory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REFERENCE = HERE/"reference/T09"
TOTALS = {"CPU-ACT": 45, "CPU-DIR-INT": 24, "CPU-DIR-MEM": 20,
          "CPU-DIR-HAZ": 24, "CPU-DIR-TRAP": 28, "CPU-DIR-CSR": 16,
          "CPU-DIFF-INT": 34, "CPU-DIFF-MEM": 33, "CPU-DIFF-TRAP": 33,
          "CPU-PIPE-HAZ": 8, "CPU-PIPE-FLUSH": 8, "CPU-PIPE-MEM": 80,
          "CPU-PIPE-RESET": 4, "CPU-PIPE-LAT": 64, "CPU-PIPE-CYCLES": 22}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_power_fields(ppa: dict) -> None:
    """Export both W and mW, including the per-seed public baseline fields."""
    for row in ppa["per_seed"]:
        row["average_power_mw"] = row["power_w"]*1000
    ppa["average_power_mw"] = statistics.median(row["average_power_mw"] for row in ppa["per_seed"])


def publish_atomic(path: Path, content: str) -> None:
    """Never expose a partially written JSON file to scoring readers."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".t09_publish_", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def qualify(ppa: dict, functional: dict, timing: dict, mutants: dict) -> None:
    if ppa.get("task_id") != "T09" or ppa.get("measurement_status") != "three_seed" or \
            ppa.get("routed") is not True:
        raise ValueError("reference needs three routed/power seeds")
    rows = ppa.get("per_seed", [])
    if [row["layout_seed"] for row in rows] != [11, 29, 47]:
        raise ValueError("reference must use seeds 11/29/47")
    for row in rows:
        if row["setup_worst_slack_ns"] < 0 or row["hold_worst_slack_ns"] < 0 or row["drc_violations"] != 0:
            raise ValueError(f"reference seed {row['layout_seed']} fails setup/hold/DRC")
    if functional.get("phase") != "scored" or functional.get("score", {}).get("full_functional_pass") is not True:
        raise ValueError("reference fails functional qualification")
    if set(functional.get("groups", {})) != set(TOTALS) or any(
            functional["groups"][name] != {"cases_passed": count, "cases_total": count}
            for name, count in TOTALS.items()):
        raise ValueError("reference functional inventory is incomplete or changed")
    if timing.get("phase") != "run" or timing.get("timing_policy") != "port_timing_v1" or \
            timing.get("cases_passed") != 22 or timing.get("cases_total") != 22 or \
            len(timing.get("outcomes", [])) != 22 or not all(row["passed"] for row in timing["outcomes"]):
        raise ValueError("reference fails 22 fixed cycle checks")
    expected_timing_names = {"continuous_addi", *(row[0] for row in case_inventory())}
    if {row.get("name") for row in timing["outcomes"]} != expected_timing_names:
        raise ValueError("reference cycle inventory duplicated or changed")
    if len(timing.get("diagnostic_probes", [])) != 4 or any("error" in row for row in timing["diagnostic_probes"]):
        raise ValueError("control-flow diagnostic probe failed functionally")
    if {row.get("name") for row in timing["diagnostic_probes"]} != {"taken_bne", "not_taken_bne", "jal", "jalr"}:
        raise ValueError("control-flow diagnostic inventory duplicated or changed")
    if any(mutants.get(key) != 21 for key in ("mutants", "compilable", "caught")) or \
            len(mutants.get("outcomes", [])) != 21 or \
            not all(row["compilable"] and row["caught"] for row in mutants["outcomes"]):
        raise ValueError("reference mutation qualification incomplete")


def verify_routes(ppa: dict) -> None:
    """Check actual immutable source/config/report files, not just JSON claims."""
    for row in ppa["per_seed"]:
        record = Path(row["route_record"])
        route = json.loads(record.read_text())
        config, sdc = record.parent/"config.mk", record.parent/"constraint.sdc"
        fields = dict(line.removeprefix("export ").split(" = ", 1)
                      for line in config.read_text().splitlines() if line.startswith("export "))
        routed_sources = [Path(value) for value in fields["VERILOG_FILES"].split()]
        # T09 currently has exactly one source, ref.sv. Fail closed on a
        # changed inventory rather than guessing the provenance of a new one.
        if len(routed_sources) != 1 or routed_sources[0].name != "ref.sv" or \
                sha(routed_sources[0]) != sha(REFERENCE/"rtl/ref.sv"):
            raise ValueError("routed source differs from the qualified reference")
        if sdc.read_text() != constraint_text("rv32i_five_stage_cpu", ("clk",), 1000, 0.20):
            raise ValueError("reference relaxed or changed timing constraints")
        digest = hashlib.sha256(config.read_bytes()+sdc.read_bytes()+routed_sources[0].read_bytes()).hexdigest()
        expected_variant = f"ic_probe_t09_wc_p1000_u10_d0.6_s{row['layout_seed']}_{digest[:10]}"
        if route["variant"] != expected_variant or Path(route["report"]).parent.name != expected_variant:
            raise ValueError("route variant/config/source digest mismatch")
        result_dir = expected_result_dir(route["report"])
        logs = Path(*["logs" if part == "results" else part for part in result_dir.parts])
        measured = report_fields(Path(route["report"]), logs/"6_report.json", 1000)
        if any(route[key] != measured[key] for key in measured):
            raise ValueError("route JSON differs from actual finish metrics/report")
        power = json.loads(Path(row["power_record"]).read_text())
        elf = HERE/"t09_data/programs/random/diff_mem_seed035_v0.elf"
        if power.get("vcd_clock_period_ps") != {"clk": 1000} or \
                power.get("workload_parameters") != {"seed": 20260928, "elf_sha256": sha(elf)}:
            raise ValueError("reference power clock or frozen workload changed")


def freeze(measurement: Path, evidence: Path) -> dict:
    before = source_hash(REFERENCE)
    original = json.loads(measurement.read_text())
    pairs = [(Path(row["route_record"]), Path(row["power_record"])) for row in original["per_seed"]]
    ppa = aggregate("T09", REFERENCE, pairs)
    if original != ppa or ppa["source_sha256"] != before:
        raise ValueError("measurement changed or belongs to another reference")
    verify_routes(ppa)
    if evidence.exists():
        raise ValueError("evidence destination already exists; preserve previous qualification")
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_t09_freeze_") as directory:
        work = Path(directory)
        commands = (
            ("functional", [sys.executable, str(HERE/"t09_check.py"), str(REFERENCE),
                            "--elapsed-seconds", "0", "--delivery-qualified", "--seed", "20260928"]),
            ("timing", [sys.executable, str(HERE/"t09_timing_check.py"), "--submission", str(REFERENCE)]),
            ("mutations", [sys.executable, str(HERE/"t09_mutation_check.py")]),
        )
        reports = {}
        for name, command in commands:
            output = work/f"{name}.json"
            with (work/f"{name}.log").open("w") as log:
                executed = subprocess.run([*command, "--output", str(output)], stdout=log,
                                          stderr=subprocess.STDOUT, timeout=1200)
            if executed.returncode or not output.is_file():
                raise ValueError(f"{name} requalification failed: " + (work/f"{name}.log").read_text()[-2000:])
            reports[name] = json.loads(output.read_text())
        qualify(ppa, reports["functional"], reports["timing"], reports["mutations"])
        if before != source_hash(REFERENCE):
            raise ValueError("reference changed during qualification")
        evidence.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, evidence)
    for row, (route_file, power_file) in zip(ppa["per_seed"], pairs):
        route = json.loads(route_file.read_text())
        result_dir = expected_result_dir(route["report"])
        logs = Path(*["logs" if part == "results" else part for part in result_dir.parts])
        destination = evidence/f"seed{row['layout_seed']}"
        destination.mkdir()
        for source, name in ((route_file, "route.json"), (power_file, "power.json"),
                             (route_file.parent/"config.mk", "config.mk"),
                             (route_file.parent/"constraint.sdc", "constraint.sdc"),
                             (Path(route["report"]), "6_finish.rpt"),
                             (logs/"6_report.json", "6_report.json"),
                             (Path(route["report"]).with_name("5_route_drc.rpt"), "5_route_drc.rpt"),
                             (power_file.parent/"power.log", "power.log"),
                             (power_file.parent/"simulation.log", "simulation.log")):
            shutil.copy2(source, destination/name)
        row.update(config_sha256=sha(destination/"config.mk"),
                   constraint_sha256=sha(destination/"constraint.sdc"),
                   finish_report_sha256=sha(destination/"6_finish.rpt"),
                   drc_report_sha256=sha(destination/"5_route_drc.rpt"),
                   power_report_sha256=sha(destination/"power.log"),
                   routed_netlist_sha256=sha(result_dir/"6_final.v"),
                   routed_spef_sha256=sha(result_dir/"6_final.spef"),
                   evidence_route_record=str((destination/"route.json").relative_to(ROOT)),
                   evidence_power_record=str((destination/"power.json").relative_to(ROOT)))
    ppa.update(qualification_status="qualified_1ghz", timing_policy_revision="port_timing_v1")
    add_power_fields(ppa)
    (evidence/"ppa.json").write_text(json.dumps(ppa, indent=2)+"\n")
    if before != source_hash(REFERENCE):
        raise ValueError("reference changed before publication")
    baseline_path = ROOT/"benchmark/ppa-baselines.json"
    baselines = json.loads(baseline_path.read_text())
    qualification = {
        "task_id": "T09", "qualification_date": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "qualification_scope": "current reference: full functional + port_timing_v1 + three-seed PPA",
        "reference_sha256": sha(REFERENCE/"rtl/ref.sv"), "source_sha256": before,
        "current_timing_policy_status": "qualified", "current_timing_report": "t09_timing_qualification.json",
        "reference_groups": {name: {"passed": row["cases_passed"], "total": row["cases_total"]}
                             for name, row in reports["functional"]["groups"].items()},
        "functional_basic": 48, "functional_edges": 27, "functional_total_normalized": 50,
        "scoring_policy": "t09_group_cycles10_v1",
        "cycle_group_normalized_points": {"full": 10, "half": 5, "zero": 0},
        "seed": 20260928,
        "eligible_mutants": 21, "killed_mutants": 21,
        "ppa_baseline_status": "qualified_1ghz", "layout_seeds": [11,29,47], "gate_clock_period_ps": 1000,
        "power_workload_id": ppa["workload_id"], "power_workload_parameters": ppa["workload_parameters"],
        "evidence_path": str(evidence.relative_to(ROOT)),
        "checker_sha256": {name: sha(HERE/name) for name in (
            "t09_check.py", "t09_timing_check.py", "t09_timing_tb.sv", "t09_mutation_check.py",
            "t09_oracle_check.py", "t09_wait_check.py", "t09_reset_check.py", "t09_spec_check.py",
            "cpu_latency_check.py", "sail_commit.py", "public_check.py", "score_run.py",
            "t09_reference_freeze.py", "ppa_aggregate.py", "ppa_probe.py", "ppa_power_probe.py",
            "score_rules.json")},
        "bus_testbench_path": "benchmark/tasks/T09/public/tb_cpu_elf.sv",
        "bus_testbench_sha256": sha(ROOT/"benchmark/tasks/T09/public/tb_cpu_elf.sv"),
        "public_latency_testbench_sha256": sha(ROOT/"benchmark/tasks/T09/public/tb.sv"),
        "oracle_manifest_sha256": {str(path.relative_to(HERE)): sha(path)
                                   for path in sorted((HERE/"t09_data").rglob("MANIFEST.json"))},
        "evidence_sha256": {str(path.relative_to(evidence)): sha(path)
                            for path in sorted(evidence.rglob("*")) if path.is_file()},
    }
    baselines["tasks"]["T09"] = ppa
    # Publish the authoritative PPA pointer last. Cross-file readers must
    # match source_sha256; a stale baseline must never qualify another RTL.
    publish_atomic(HERE/"t09_timing_qualification.json", (evidence/"timing.json").read_text())
    publish_atomic(HERE/"t09_qualification.json", json.dumps(qualification, indent=2)+"\n")
    publish_atomic(baseline_path, json.dumps(baselines, indent=2)+"\n")
    return {"status": "qualified_1ghz", "source_sha256": before, "evidence": str(evidence),
            "setup_worst_slack_ns": ppa["setup_worst_slack_ns"],
            "hold_worst_slack_ns": ppa["hold_worst_slack_ns"], "drc_violations": ppa["drc_violations"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurement", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    if not evidence.is_relative_to(HERE/"fixtures"):
        parser.error("publish evidence inside evaluator/fixtures")
    print(json.dumps(freeze(args.measurement.resolve(), evidence), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
